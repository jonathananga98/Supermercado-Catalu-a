from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from .models import Producto, Categoria
from .forms import RegistroForm
import urllib.parse
import uuid


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

    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())

    context = {
        'page_obj': page_obj,
        'productos': page_obj,
        'categorias': categorias,
        'categoria_activa': int(categoria_seleccionada) if categoria_seleccionada else None,
        'cart_count': cart_count,
    }
    
    return render(request, 'productos.html', context)


# ==========================================
# 2. MÓDULO DEL CARRITO DE COMPRAS (SESIONES)
# ==========================================
def agregar_carrito(request, producto_id):
    """
    Añade un producto a la sesión del navegador.
    """
    cart = request.session.get('cart', {})
    str_id = str(producto_id)

    if str_id in cart:
        cart[str_id] += 1
    else:
        cart[str_id] = 1

    request.session['cart'] = cart
    request.session.modified = True

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
    Captura los datos, formatea un recibo detallado sin emojis ni códigos,
    y redirige a WhatsApp.
    """
    cart = request.session.get('cart', {})
    
    if not cart:
        return redirect('lista_productos')

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        direccion = request.POST.get('direccion')
        metodo_pago = request.POST.get('metodo_pago')
        notas = request.POST.get('notas', 'Ninguna')
        
        # Estructura visual del mensaje (texto plano)
        mensaje = "*NUEVO PEDIDO*\n"
        mensaje += "*Supermercado Cataluña*\n\n"
        mensaje += f"*Cliente:* {nombre}\n"
        mensaje += f"*Dirección:* {direccion}\n"
        mensaje += f"*Pago:* {metodo_pago}\n"
        
        if notas.strip():
            mensaje += f"*Notas:* {notas}\n"
            
        mensaje += "\n*DETALLE DE LA COMPRA:*\n"
        
        total_general = 0
        for prod_id, cantidad in cart.items():
            producto = get_object_or_404(Producto, id=prod_id)
            subtotal = producto.precio_venta * cantidad
            total_general += subtotal
            mensaje += f"- {cantidad}x {producto.nombre} - ${subtotal:,.0f}\n"
        
        mensaje += f"\n========================\n"
        mensaje += f"*TOTAL A PAGAR: ${total_general:,.0f}*\n"
        mensaje += f"========================\n\n"
        mensaje += "¡Hola! Confirmo mi pedido. Quedo atento/a a la entrega."

        # Recuerda cambiar el número de teléfono
        numero_whatsapp = "3202656464" 
        mensaje_codificado = urllib.parse.quote(mensaje)
        url_whatsapp = f"https://wa.me/{numero_whatsapp}?text={mensaje_codificado}"

        request.session['cart'] = {}
        request.session.modified = True

        return redirect(url_whatsapp)

    total_general = sum(
        get_object_or_404(Producto, id=prod_id).precio_venta * cantidad 
        for prod_id, cantidad in cart.items()
    )

    return render(request, 'checkout.html', {'total_general': total_general})

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