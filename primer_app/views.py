import urllib.parse
import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .forms import RegistroForm
from .models import Categoria, Producto
from .serializers import CategoriaSerializer, ProductoSerializer
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from decimal import Decimal
from django.db import transaction
from .models import Categoria, Producto, ZonaDomicilio, Pedido, DetallePedido

# ==========================================
# 1. CATÁLOGO DE PRODUCTOS (VISTA PRINCIPAL)
# ==========================================
def lista_productos(request):
    """
    Muestra el catálogo del supermercado con soporte para:
    - Filtrado por categoría.
    - Buscador de productos por palabra clave.
    - Paginación (50 productos por página).
    - Conteo de elementos guardados en la sesión del carrito.
    """
    categorias = Categoria.objects.all()
    
    categoria_seleccionada = request.GET.get('categoria')
    busqueda = request.GET.get('q')

    productos = Producto.objects.all()

    if categoria_seleccionada:
        productos = productos.filter(categoria_id=categoria_seleccionada)

    if busqueda:
        productos = productos.filter(nombre__icontains=busqueda)

    paginator = Paginator(productos, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    custom_page_range = paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)

    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())

    context = {
        'page_obj': page_obj,
        'productos': page_obj,
        'categorias': categorias,
        'categoria_activa': int(categoria_seleccionada) if categoria_seleccionada else None,
        'cart_count': cart_count,
        'custom_page_range': custom_page_range,
    }

    return render(request, 'productos.html', context)


# ==========================================
# 2. MÓDULO DEL CARRITO DE COMPRAS (SESIONES)
# ==========================================
def agregar_carrito(request, producto_id):
    """
    Añade un producto a la sesión del navegador validando el stock disponible.
    """
    producto = get_object_or_404(Producto, id=producto_id)
    cart = request.session.get('cart', {})
    str_id = str(producto_id)

    cantidad_actual = cart.get(str_id, 0)

    if cantidad_actual < producto.stock:
        cart[str_id] = cantidad_actual + 1
        request.session['cart'] = cart
        request.session.modified = True
    else:
        messages.warning(request, f"Solo hay {producto.stock} unidades disponibles de {producto.nombre}.")

    return redirect(request.META.get('HTTP_REFERER', 'lista_productos'))


def restar_carrito(request, producto_id):
    """
    Disminuye la cantidad de un producto en 1.
    """
    cart = request.session.get('cart', {})
    str_id = str(producto_id)

    if str_id in cart:
        if cart[str_id] > 1:
            cart[str_id] -= 1
        else:
            del cart[str_id]

    request.session['cart'] = cart
    request.session.modified = True
    return redirect('ver_carrito')


def eliminar_carrito(request, producto_id):
    """
    Elimina por completo un producto del carrito.
    """
    cart = request.session.get('cart', {})
    str_id = str(producto_id)

    if str_id in cart:
        del cart[str_id]

    request.session['cart'] = cart
    request.session.modified = True
    return redirect('ver_carrito')

# Alias por compatibilidad de nombres
eliminar_del_carrito = eliminar_carrito


def ver_carrito(request):
    """
    Calcula el desglose del carrito y renderiza 'carrito.html'.
    """
    cart = request.session.get('cart', {})
    items_carrito = []
    total_general = 0

    for prod_id, cantidad in cart.items():
        producto = get_object_or_404(Producto, id=prod_id)
        subtotal = producto.precio_venta * cantidad
        total_general += subtotal

        items_carrito.append({
            'producto': producto,
            'cantidad': cantidad,
            'subtotal': subtotal
        })

    context = {
        'items_carrito': items_carrito,
        'total_general': total_general,
    }
    return render(request, 'carrito.html', context)




def procesar_pedido(request):
    """
    Calcula el total según el tipo de entrega (Domicilio $5.000 o Recoger en tienda $0),
    descuenta el inventario en BD, vacía la sesión del carrito y redirige a WhatsApp.
    """
    cart = request.session.get('cart', {})

    if not cart:
        return redirect('lista_productos')

    COSTO_DOMICILIO_BASE = 5000

    # Calcular el subtotal
    subtotal_productos = 0
    items_resumen = []

    for prod_id, cantidad in cart.items():
        producto = get_object_or_404(Producto, id=prod_id)
        subtotal = producto.precio_venta * cantidad
        subtotal_productos += subtotal
        items_resumen.append({
            'producto': producto,
            'cantidad': cantidad,
            'subtotal': subtotal
        })

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        telefono = request.POST.get('telefono', '')
        tipo_entrega = request.POST.get('tipo_entrega', 'domicilio')
        direccion = request.POST.get('direccion', '')
        metodo_pago = request.POST.get('metodo_pago')
        notas = request.POST.get('notas', 'Ninguna')

        if tipo_entrega == 'recoger':
            costo_domicilio = 0
            texto_entrega = " Recoger en tienda (Sin costo)"
        else:
            costo_domicilio = COSTO_DOMICILIO_BASE
            texto_entrega = f" Domicilio (${COSTO_DOMICILIO_BASE:,.0f})"

        total_final = subtotal_productos + costo_domicilio

        mensaje = "*NUEVO PEDIDO*\n"
        mensaje += "*Supermercado Cataluña*\n\n"
        mensaje += f"*Cliente:* {nombre}\n"
        if telefono.strip():
            mensaje += f"*Teléfono:* {telefono}\n"
        mensaje += f"*Entrega:* {texto_entrega}\n"

        if tipo_entrega == 'domicilio' and direccion.strip():
            mensaje += f"*Dirección:* {direccion}\n"

        mensaje += f"*Pago:* {metodo_pago}\n"

        if notas.strip():
            mensaje += f"*Notas:* {notas}\n"

        mensaje += "\n*DETALLE DE LA COMPRA:*\n"

        for item in items_resumen:
            prod = item['producto']
            cant = item['cantidad']
            sub = item['subtotal']
            mensaje += f"- {cant}x {prod.nombre} - ${sub:,.0f}\n"

            # 1. Descuento de inventario en la base de datos
            prod.stock = max(0, prod.stock - cant)
            prod.save()

        mensaje += "\n----------------------\n"
        mensaje += f"Subtotal productos: ${subtotal_productos:,.0f}\n"
        mensaje += f"Servicio a domicilio: ${costo_domicilio:,.0f}\n"
        mensaje += f"*TOTAL A PAGAR: ${total_final:,.0f}*\n"

        # 2. Vaciar el carrito de la sesión tras procesar el pedido
        request.session['cart'] = {}
        request.session.modified = True

        # Redirección a WhatsApp
        numero_whatsapp = "573202656464"
        mensaje_encoded = urllib.parse.quote(mensaje)
        url_whatsapp = f"https://wa.me/{numero_whatsapp}?text={mensaje_encoded}"

        return redirect(url_whatsapp)

    context = {
        'items_resumen': items_resumen,
        'subtotal_productos': subtotal_productos,
        'costo_domicilio': COSTO_DOMICILIO_BASE,
        'total_general': subtotal_productos + COSTO_DOMICILIO_BASE,
    }
    return render(request, 'checkout.html', context)

# ==========================================
# 3. AUTENTICACIÓN Y REGISTRO DE USUARIOS
# ==========================================
def registro_usuario(request):
    """
    Maneja el registro de nuevos usuarios.
    """
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            return redirect('lista_productos')
    else:
        form = RegistroForm()

    return render(request, 'registro.html', {'form': form})


def iniciar_sesion(request):
    """
    Maneja el inicio de sesión.
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            usuario = form.get_user()
            login(request, usuario)
            return redirect('lista_productos')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})


def cerrar_sesion(request):
    """
    Cierra la sesión del usuario.
    """
    logout(request)
    return redirect('lista_productos')


# ========================================================
# 4. API REST CON DJANGO REST FRAMEWORK (DRF)
# ========================================================


@api_view(['GET'])
def api_lista_categorias(request):
    """
    Devuelve todas las categorías disponibles en formato JSON.
    """
    categorias = Categoria.objects.all()
    serializer = CategoriaSerializer(categorias, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def api_lista_productos(request):
    """
    Endpoint REST para consultar el catálogo de Supermercado Cataluña.
    Soporta filtrado por ?categoria=ID y búsqueda por ?q=texto (nombre o código).
    """
    productos = Producto.objects.select_related('categoria').all()
    categoria_id = request.GET.get('categoria')
    query = request.GET.get('q')

    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)

    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(codigo__icontains=query)
        )[:15]

    serializer = ProductoSerializer(productos, many=True, context={'request': request})
    return Response({
        'total': productos.count(),
        'resultados': serializer.data
    })


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def api_agregar_carrito(request, producto_id):
    """
    Endpoint REST (POST) para añadir productos al carrito sin recargar la página.
    """
    producto = get_object_or_404(Producto, id=producto_id)
    cart = request.session.get('cart', {})
    str_id = str(producto_id)
    cantidad_actual = cart.get(str_id, 0)

    if cantidad_actual < producto.stock:
        cart[str_id] = cantidad_actual + 1
        request.session['cart'] = cart
        request.session.modified = True
        return Response({
            'ok': True,
            'cart_count': sum(cart.values()),
            'producto': producto.nombre,
            'cantidad_en_carrito': cart[str_id],
            'mensaje': f'¡{producto.nombre} agregado al carrito!'
        }, status=status.HTTP_200_OK)

    return Response({
        'ok': False,
        'cart_count': sum(cart.values()),
        'mensaje': f'Stock insuficiente. Solo quedan {producto.stock} unidades de {producto.nombre}.'
    }, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def api_actualizar_carrito(request, producto_id):
    """
    Endpoint REST (POST) para sumar, restar o eliminar ítems del carrito sin recargar.
    Espera JSON: {"accion": "sumar" | "restar" | "eliminar"}
    """
    producto = get_object_or_404(Producto, id=producto_id)
    accion = request.data.get('accion')
    cart = request.session.get('cart', {})
    str_id = str(producto_id)
    cantidad_actual = cart.get(str_id, 0)
    mensaje = ''

    if accion == 'sumar':
        if cantidad_actual < producto.stock:
            cart[str_id] = cantidad_actual + 1
        else:
            return Response({
                'ok': False,
                'mensaje': f'Stock máximo alcanzado ({producto.stock} disponibles).'
            }, status=status.HTTP_400_BAD_REQUEST)
    elif accion == 'restar':
        if cantidad_actual > 1:
            cart[str_id] = cantidad_actual - 1
        else:
            cart.pop(str_id, None)
    elif accion == 'eliminar':
        cart.pop(str_id, None)

    request.session['cart'] = cart
    request.session.modified = True

    nueva_cantidad = cart.get(str_id, 0)
    subtotal_item = producto.precio_venta * nueva_cantidad

    productos_en_carrito = Producto.objects.filter(id__in=cart.keys())
    total_general = sum(p.precio_venta * cart[str(p.id)] for p in productos_en_carrito)

    return Response({
        'ok': True,
        'producto_id': producto_id,
        'cantidad': nueva_cantidad,
        'subtotal_item': f"{subtotal_item:.0f}",
        'total_general': f"{total_general:.0f}",
        'cart_count': sum(cart.values()),
        'mensaje': mensaje
    }, status=status.HTTP_200_OK)
    
    
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def api_ver_carrito(request):
    cart = request.session.get('cart', {})
    items = []
    total_general = 0
    for prod_id, cantidad in cart.items():
        producto = Producto.objects.filter(id=prod_id).first()
        if producto:
            subtotal = float(producto.precio_venta) * cantidad
            total_general += subtotal
            imagen_url = request.build_absolute_uri(producto.imagen.url) if producto.imagen else None
            items.append({
                'producto_id': producto.id,
                'nombre': producto.nombre,
                'precio_venta': float(producto.precio_venta),
                'stock': producto.stock,
                'imagen_url': imagen_url,
                'cantidad': cantidad,
                'subtotal': subtotal
            })
    return Response({
        'items': items,
        'total_general': total_general,
        'cart_count': sum(cart.values())
    })
    
    
@api_view(['GET'])
def api_zonas_domicilio(request):
    if not ZonaDomicilio.objects.exists():
        ZonaDomicilio.objects.bulk_create([
            ZonaDomicilio(
                nombre='Zona 1: Cercana (Sector Estadio)',
                descripcion='Calles 40 a 50, Carreras 5 a 15',
                tarifa_base=Decimal('3500'),
                descuento_compra_grande=Decimal('1000'),
                monto_minimo_descuento=Decimal('90000'),
            ),
            ZonaDomicilio(
                nombre='Zona 2: Intermedia / Centro',
                descripcion='Calles 8 a 40 (incluye Centro y barrios cercanos)',
                tarifa_base=Decimal('5000'),
                descuento_compra_grande=Decimal('1000'),
                monto_minimo_descuento=Decimal('90000'),
            ),
            ZonaDomicilio(
                nombre='Zona 3: Periferia / Afueras',
                descripcion='Calle 60 hacia abajo, Cra 1 a 5 (Llano Lindo, La Bendición, Morichal)',
                tarifa_base=Decimal('7000'),
                descuento_compra_grande=Decimal('1000'),
                monto_minimo_descuento=Decimal('90000'),
            ),
        ])

    zonas = ZonaDomicilio.objects.filter(activa=True).values(
        'id', 'nombre', 'descripcion', 'tarifa_base', 'descuento_compra_grande', 'monto_minimo_descuento'
    )
    return Response(list(zonas))


@api_view(['POST'])
@transaction.atomic
def api_checkout(request):
    data = request.data
    items = data.get('items', [])
    nombre = (data.get('nombre') or '').strip()
    telefono = (data.get('telefono') or '').strip()
    tipo_entrega = data.get('tipo_entrega', 'domicilio')
    zona_id = data.get('zona_id')
    direccion = (data.get('direccion') or '').strip()
    metodo_pago = (data.get('metodo_pago') or 'Efectivo').strip()
    notas = (data.get('notas') or '').strip()

    if not items:
        return Response({'error': 'El carrito está vacío.'}, status=400)
    if not nombre or not telefono:
        return Response({'error': 'Nombre y teléfono son obligatorios.'}, status=400)
    if tipo_entrega == 'domicilio' and not direccion:
        return Response({'error': 'La dirección es obligatoria para envío a domicilio.'}, status=400)

    subtotal_productos = Decimal('0')
    detalles_a_crear = []

    for item in items:
        prod_id = item.get('id')
        cantidad = int(item.get('cantidad', 1))
        if cantidad <= 0:
            continue

        producto = Producto.objects.select_for_update().filter(id=prod_id).first()
        if not producto:
            return Response({'error': f'Producto ID {prod_id} no encontrado.'}, status=404)
        if producto.stock < cantidad:
            return Response(
                {'error': f'Stock insuficiente para "{producto.nombre}". Disponible: {producto.stock}.'},
                status=400
            )

        sub = producto.precio_venta * cantidad
        subtotal_productos += sub
        detalles_a_crear.append((producto, cantidad, producto.precio_venta, sub))

    zona = None
    costo_domicilio = Decimal('0')
    if tipo_entrega == 'recoger':
        texto_entrega = 'Recoger en tienda (Sin costo)'
    else:
        zona = ZonaDomicilio.objects.filter(id=zona_id, activa=True).first()
        if zona:
            costo_domicilio = zona.calcular_envio(subtotal_productos)
            texto_entrega = f"Domicilio - {zona.nombre} (${costo_domicilio:,.0f})"
        else:
            costo_domicilio = Decimal('4500')
            texto_entrega = f"Domicilio (${costo_domicilio:,.0f})"

    total_final = subtotal_productos + costo_domicilio

    pedido = Pedido.objects.create(
        nombre_cliente=nombre,
        telefono=telefono,
        tipo_entrega=tipo_entrega,
        zona=zona,
        direccion=direccion if tipo_entrega == 'domicilio' else '',
        metodo_pago=metodo_pago,
        notas=notas,
        subtotal=subtotal_productos,
        costo_envio=costo_domicilio,
        total=total_final,
    )

    mensaje = f"*NUEVO PEDIDO #{pedido.id}*\n"
    mensaje += "*Supermercado Cataluña*\n\n"
    mensaje += f"*Cliente:* {nombre}\n"
    mensaje += f"*Teléfono:* {telefono}\n"
    mensaje += f"*Entrega:* {texto_entrega}\n"
    if tipo_entrega == 'domicilio' and direccion:
        mensaje += f"*Dirección:* {direccion}\n"
    mensaje += f"*Pago:* {metodo_pago}\n"
    if notas:
        mensaje += f"*Notas:* {notas}\n"

    mensaje += "\n*DETALLE DE LA COMPRA:*\n"
    for producto, cantidad, precio_unit, sub in detalles_a_crear:
        DetallePedido.objects.create(
            pedido=pedido,
            producto=producto,
            nombre_producto=producto.nombre,
            cantidad=cantidad,
            precio_unitario=precio_unit,
            subtotal=sub,
        )
        producto.stock = max(0, producto.stock - cantidad)
        producto.save()
        mensaje += f"- {cantidad}x {producto.nombre} - ${sub:,.0f}\n"

    mensaje += "\n----------------------\n"
    mensaje += f"Subtotal productos: ${subtotal_productos:,.0f}\n"
    mensaje += f"Servicio a domicilio: ${costo_domicilio:,.0f}\n"
    mensaje += f"*TOTAL A PAGAR: ${total_final:,.0f}*\n"

    numero_whatsapp = "573202656464"
    url_whatsapp = f"https://wa.me/{numero_whatsapp}?text={urllib.parse.quote(mensaje)}"

    return Response({
        'pedido_id': pedido.id,
        'subtotal': float(subtotal_productos),
        'costo_envio': float(costo_domicilio),
        'total': float(total_final),
        'url_whatsapp': url_whatsapp,
    }, status=201)