from rest_framework import serializers
from .models import Producto, Categoria


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre']


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(
        source='categoria.nombre',
        read_only=True,
        default='General'
    )
    imagen_url = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id',
            'codigo',
            'nombre',
            'precio_venta',
            'precio_mayoreo',
            'tipo_venta',
            'stock',
            'categoria',
            'categoria_nombre',
            'imagen_url',
        ]

    def get_imagen_url(self, obj):
        if obj.imagen:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.imagen.url)
            return obj.imagen.url
        return None


# ---------------------------------------------------------------------------
# Pedidos y autenticación de clientes
# ---------------------------------------------------------------------------
import re

from django.contrib.auth.models import User

MIN_PASSWORD = 6


def normalizar_telefono(valor):
    """Deja solo dígitos y quita el indicativo 57 de Colombia (57 + 10 dígitos)."""
    digitos = re.sub(r'\D', '', valor or '')
    if len(digitos) == 12 and digitos.startswith('57'):
        digitos = digitos[2:]
    return digitos


def validar_telefono(valor):
    digitos = normalizar_telefono(valor)
    if not 7 <= len(digitos) <= 13:
        raise serializers.ValidationError('Ingresa un teléfono válido (ej. 310 123 4567).')
    return digitos


class ItemPedidoSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    cantidad = serializers.IntegerField(min_value=1, max_value=999)


class PedidoCreateSerializer(serializers.Serializer):
    """Payload que envía Angular a POST /api/pedidos/."""
    nombre = serializers.CharField(max_length=150)
    telefono = serializers.CharField(max_length=30)
    tipo_entrega = serializers.ChoiceField(choices=['domicilio', 'recoger'], default='domicilio')
    zona_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    direccion = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    metodo_pago = serializers.CharField(max_length=100, required=False, allow_blank=True, default='Efectivo')
    notas = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    items = ItemPedidoSerializer(many=True, allow_empty=False)
    # Casilla opcional "Crear cuenta con estos datos"
    crear_cuenta = serializers.BooleanField(required=False, default=False)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')

    def validate_nombre(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError('Ingresa tu nombre completo.')
        return valor

    def validate_telefono(self, valor):
        validar_telefono(valor)
        return valor.strip()

    def validate(self, attrs):
        if attrs['tipo_entrega'] == 'domicilio' and not attrs['direccion'].strip():
            raise serializers.ValidationError({'direccion': 'La dirección es obligatoria para el domicilio.'})
        if attrs['crear_cuenta'] and len(attrs['password']) < MIN_PASSWORD:
            raise serializers.ValidationError(
                {'password': f'La contraseña debe tener al menos {MIN_PASSWORD} caracteres.'}
            )
        attrs['direccion'] = attrs['direccion'].strip() if attrs['tipo_entrega'] == 'domicilio' else ''
        attrs['metodo_pago'] = attrs['metodo_pago'].strip() or 'Efectivo'
        return attrs


class RegistroSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150)
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True)

    def validate_nombre(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError('Ingresa tu nombre.')
        return valor

    def validate_password(self, valor):
        if len(valor) < MIN_PASSWORD:
            raise serializers.ValidationError(f'La contraseña debe tener al menos {MIN_PASSWORD} caracteres.')
        return valor

    def validate(self, attrs):
        telefono = attrs.get('telefono', '').strip()
        email = attrs.get('email', '').strip().lower()
        if not telefono and not email:
            raise serializers.ValidationError({'telefono': 'Ingresa tu teléfono o tu correo.'})
        if telefono:
            attrs['telefono_normalizado'] = validar_telefono(telefono)
        attrs['telefono'] = telefono
        attrs['email'] = email
        return attrs


class LoginSerializer(serializers.Serializer):
    # Acepta "identificador" (teléfono o correo); también "telefono" / "email" por comodidad.
    identificador = serializers.CharField(required=False, allow_blank=True, default='')
    telefono = serializers.CharField(required=False, allow_blank=True, default='')
    email = serializers.CharField(required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        ident = (attrs['identificador'] or attrs['telefono'] or attrs['email']).strip()
        if not ident:
            raise serializers.ValidationError({'identificador': 'Ingresa tu teléfono o correo.'})
        attrs['ident'] = ident
        return attrs


def usuario_a_dict(user):
    perfil = getattr(user, 'perfil', None)
    return {
        'id': user.id,
        'nombre': user.first_name or user.username,
        'telefono': perfil.telefono if perfil else '',
        'email': user.email,
        'direccion': perfil.direccion if perfil else '',
    }
