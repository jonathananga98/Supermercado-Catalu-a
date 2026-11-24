"""
API para Angular: pedidos (invitado o autenticado) y cuentas de clientes.

    POST /api/pedidos/          Crea un pedido y descuenta stock (AllowAny, token opcional)
    POST /api/auth/registro/    Crea cuenta de cliente y devuelve token
    POST /api/auth/login/       Inicia sesión y devuelve token
    GET  /api/auth/perfil/      Datos del cliente autenticado (valida la sesión guardada)
    POST /api/auth/logout/      Invalida el token actual
"""
import urllib.parse
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .authentication import TokenOpcional
from .models import DetallePedido, PerfilCliente, Pedido, Producto, ZonaDomicilio
from .serializers import (
    LoginSerializer,
    PedidoCreateSerializer,
    RegistroSerializer,
    normalizar_telefono,
    usuario_a_dict,
)

ENVIO_POR_DEFECTO = Decimal('4500')  # Se usa solo si el domicilio llega sin una zona válida


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
class _ThrottlePorIP(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class AuthThrottle(_ThrottlePorIP):
    scope = 'auth'      # frena fuerza bruta en login / registro


class PedidosThrottle(_ThrottlePorIP):
    scope = 'pedidos'   # frena pedidos basura que vacíen el stock


def _primer_error(errores):
    """Convierte los errores de DRF en un único texto legible para mostrar en el front."""
    if isinstance(errores, dict):
        for valor in errores.values():
            return _primer_error(valor)
    if isinstance(errores, (list, tuple)):
        for valor in errores:
            return _primer_error(valor)
    return str(errores)


def _error(mensaje, http_status=status.HTTP_400_BAD_REQUEST, **extra):
    return Response({'error': mensaje, **extra}, status=http_status)


class ErrorPedido(Exception):
    """Se lanza dentro de transaction.atomic() para revertir todo el pedido."""

    def __init__(self, mensaje, http_status=status.HTTP_400_BAD_REQUEST, **extra):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http_status = http_status
        self.extra = extra


def _respuesta_sesion(user, http_status=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    return Response({'token': token.key, 'usuario': usuario_a_dict(user)}, status=http_status)


def _buscar_usuario(identificador):
    """Busca por correo (si trae @) o por teléfono normalizado, con respaldo por username."""
    identificador = identificador.strip()
    if '@' in identificador:
        return User.objects.filter(email__iexact=identificador).first() \
            or User.objects.filter(username__iexact=identificador).first()
    digitos = normalizar_telefono(identificador)
    return (
        User.objects.filter(username=digitos).first()
        or User.objects.filter(perfil__telefono=digitos).first()
        or User.objects.filter(username__iexact=identificador).first()
    )


def _crear_usuario(nombre, telefono, email, password):
    """Crea User + PerfilCliente. Devuelve (user, None) o (None, mensaje_de_error)."""
    telefono_norm = normalizar_telefono(telefono)
    username = telefono_norm or email.lower()

    if User.objects.filter(username=username).exists() or (
        telefono_norm and PerfilCliente.objects.filter(telefono=telefono_norm).exists()
    ):
        return None, 'Ya existe una cuenta con ese teléfono. Inicia sesión.'
    if email and User.objects.filter(email__iexact=email).exists():
        return None, 'Ya existe una cuenta con ese correo. Inicia sesión.'

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, email=email, password=password, first_name=nombre[:150]
            )
            PerfilCliente.objects.create(user=user, telefono=telefono_norm)
    except IntegrityError:
        return None, 'Ya existe una cuenta con esos datos. Inicia sesión.'
    return user, None


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
def _registrar_pedido(datos, usuario):
    """
    Todo o nada: valida stock, guarda el pedido con su detalle y descuenta inventario.
    Debe llamarse dentro de transaction.atomic().
    """
    # Une líneas repetidas del mismo producto
    cantidades = {}
    for item in datos['items']:
        cantidades[item['id']] = cantidades.get(item['id'], 0) + item['cantidad']

    # Bloquea las filas (en orden, para evitar deadlocks) mientras dura la transacción
    productos = {
        p.id: p
        for p in Producto.objects.select_for_update().filter(id__in=cantidades.keys()).order_by('id')
    }

    lineas = []
    subtotal = Decimal('0')
    for prod_id, cantidad in cantidades.items():
        producto = productos.get(prod_id)
        if producto is None:
            raise ErrorPedido(
                'Uno de los productos de tu carrito ya no está disponible.',
                status.HTTP_404_NOT_FOUND, producto_id=prod_id,
            )
        if producto.stock < cantidad:
            raise ErrorPedido(
                f'Stock insuficiente para "{producto.nombre}". Disponible: {max(producto.stock, 0)}.',
                status.HTTP_409_CONFLICT, producto_id=prod_id, disponible=max(producto.stock, 0),
            )
        linea_subtotal = producto.precio_venta * cantidad
        subtotal += linea_subtotal
        lineas.append((producto, cantidad, producto.precio_venta, linea_subtotal))

    zona = None
    if datos['tipo_entrega'] == 'recoger':
        costo_envio = Decimal('0')
        texto_entrega = 'Recoger en tienda (sin costo)'
    else:
        zona = ZonaDomicilio.objects.filter(id=datos.get('zona_id'), activa=True).first()
        if zona:
            costo_envio = zona.calcular_envio(subtotal)
            texto_entrega = f'Domicilio - {zona.nombre} (${costo_envio:,.0f})'
        else:
            costo_envio = ENVIO_POR_DEFECTO
            texto_entrega = f'Domicilio (${costo_envio:,.0f})'

    pedido = Pedido.objects.create(
        usuario=usuario if (usuario and usuario.is_authenticated) else None,
        nombre_cliente=datos['nombre'],
        telefono=datos['telefono'],
        tipo_entrega=datos['tipo_entrega'],
        zona=zona,
        direccion=datos['direccion'],
        metodo_pago=datos['metodo_pago'],
        notas=datos['notas'].strip(),
        subtotal=subtotal,
        costo_envio=costo_envio,
    )  # Pedido.save() calcula el total

    for producto, cantidad, precio, linea_subtotal in lineas:
        DetallePedido.objects.create(
            pedido=pedido, producto=producto, nombre_producto=producto.nombre,
            cantidad=cantidad, precio_unitario=precio, subtotal=linea_subtotal,
        )
        # UPDATE condicional: aunque haya compras simultáneas, el stock jamás queda negativo
        descontados = Producto.objects.filter(pk=producto.pk, stock__gte=cantidad).update(
            stock=F('stock') - cantidad
        )
        if descontados == 0:
            raise ErrorPedido(
                f'Stock insuficiente para "{producto.nombre}".',
                status.HTTP_409_CONFLICT, producto_id=producto.pk,
            )

    return pedido, lineas, texto_entrega


def _mensaje_whatsapp(pedido, lineas, texto_entrega):
    m = f'*NUEVO PEDIDO {pedido.codigo}*\n'
    m += '*Supermercado Cataluña*\n\n'
    m += f'*Cliente:* {pedido.nombre_cliente}\n'
    m += f'*Teléfono:* {pedido.telefono}\n'
    m += f'*Entrega:* {texto_entrega}\n'
    if pedido.tipo_entrega == 'domicilio' and pedido.direccion:
        m += f'*Dirección:* {pedido.direccion}\n'
    m += f'*Pago:* {pedido.metodo_pago}\n'
    if pedido.notas:
        m += f'*Notas:* {pedido.notas}\n'
    m += '\n*DETALLE DE LA COMPRA:*\n'
    for producto, cantidad, _precio, sub in lineas:
        m += f'- {cantidad}x {producto.nombre} - ${sub:,.0f}\n'
    m += '\n----------------------\n'
    m += f'Subtotal productos: ${pedido.subtotal:,.0f}\n'
    m += f'Servicio a domicilio: ${pedido.costo_envio:,.0f}\n'
    m += f'*TOTAL A PAGAR: ${pedido.total:,.0f}*\n'
    return m


@api_view(['POST'])
@authentication_classes([TokenOpcional])
@permission_classes([AllowAny])
@throttle_classes([PedidosThrottle])
def crear_pedido(request):
    """
    POST /api/pedidos/  -> 201 Created

    {
      "nombre": "...", "telefono": "...", "tipo_entrega": "domicilio|recoger",
      "zona_id": 1, "direccion": "...", "metodo_pago": "...", "notas": "",
      "items": [{"id": 10, "cantidad": 2}],
      "crear_cuenta": true, "password": "secreto"      (opcionales)
    }
    """
    serializer = PedidoCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return _error(_primer_error(serializer.errors), detalle=serializer.errors)
    datos = serializer.validated_data

    try:
        with transaction.atomic():
            pedido, lineas, texto_entrega = _registrar_pedido(datos, request.user)
    except ErrorPedido as e:
        return _error(e.mensaje, e.http_status, **e.extra)

    respuesta = {
        'pedido_id': pedido.id,
        'codigo': pedido.codigo,
        'subtotal': float(pedido.subtotal),
        'costo_envio': float(pedido.costo_envio),
        'total': float(pedido.total),
        'estado': pedido.estado,
    }

    # --- Cuenta del cliente (el pedido ya está guardado: nada de esto puede tumbarlo) ---
    usuario = request.user if request.user.is_authenticated else None
    if usuario is None and datos['crear_cuenta']:
        usuario, motivo = _crear_usuario(
            datos['nombre'], datos['telefono'], datos.get('email', '').strip().lower(), datos['password']
        )
        if usuario:
            Pedido.objects.filter(pk=pedido.pk).update(usuario=usuario)
            token, _ = Token.objects.get_or_create(user=usuario)
            respuesta['cuenta'] = {'creada': True, 'mensaje': 'Cuenta creada. ¡Ya quedaste con sesión iniciada!'}
            respuesta['sesion'] = {'token': token.key, 'usuario': usuario_a_dict(usuario)}
        else:
            respuesta['cuenta'] = {'creada': False, 'mensaje': f'Pedido registrado, pero no se creó la cuenta: {motivo}'}

    # Guarda la última dirección/teléfono para autocompletar la próxima compra
    if usuario is not None:
        perfil, _ = PerfilCliente.objects.get_or_create(user=usuario)
        cambios = []
        if pedido.direccion and perfil.direccion != pedido.direccion:
            perfil.direccion = pedido.direccion
            cambios.append('direccion')
        if not perfil.telefono and normalizar_telefono(pedido.telefono):
            perfil.telefono = normalizar_telefono(pedido.telefono)
            cambios.append('telefono')
        if cambios:
            perfil.save(update_fields=cambios)
        if 'sesion' in respuesta:
            respuesta['sesion']['usuario'] = usuario_a_dict(usuario)

    mensaje = _mensaje_whatsapp(pedido, lineas, texto_entrega)
    numero = getattr(settings, 'WHATSAPP_NUMERO', '573202656464')
    respuesta['mensaje_whatsapp'] = mensaje
    respuesta['url_whatsapp'] = f'https://wa.me/{numero}?text={urllib.parse.quote(mensaje)}'
    return Response(respuesta, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Autenticación de clientes
# ---------------------------------------------------------------------------
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def registro_cliente(request):
    serializer = RegistroSerializer(data=request.data)
    if not serializer.is_valid():
        return _error(_primer_error(serializer.errors), detalle=serializer.errors)
    d = serializer.validated_data

    user, motivo = _crear_usuario(d['nombre'], d['telefono'], d['email'], d['password'])
    if user is None:
        return _error(motivo, status.HTTP_409_CONFLICT)
    return _respuesta_sesion(user, status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def login_cliente(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return _error(_primer_error(serializer.errors), detalle=serializer.errors)
    d = serializer.validated_data

    candidato = _buscar_usuario(d['ident'])
    user = authenticate(request, username=candidato.username, password=d['password']) if candidato else None
    if user is None or not user.is_active:
        return _error('Teléfono/correo o contraseña incorrectos.', status.HTTP_401_UNAUTHORIZED)
    return _respuesta_sesion(user)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def perfil_cliente(request):
    return Response({'usuario': usuario_a_dict(request.user)})


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def logout_cliente(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
