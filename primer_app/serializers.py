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