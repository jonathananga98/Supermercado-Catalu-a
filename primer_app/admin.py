from django.contrib import admin
from django.contrib.admin.helpers import ActionForm
from django import forms
from django.utils.html import format_html
from .models import Categoria, Producto
from .models import Categoria, Producto, ZonaDomicilio, Pedido, DetallePedido, PerfilCliente

# 1. Creamos un formulario en la acción para elegir a qué categoría cambiar
class AsignarCategoriaForm(ActionForm):
    nueva_categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        label="Categoría destino"
    )

# 2. Creamos la acción en lote que lee la categoría seleccionada
@admin.action(description='Cambiar categoría a los productos seleccionados')
def cambiar_categoria_lote(modeladmin, request, queryset):
    categoria_id = request.POST.get('nueva_categoria')
    
    if categoria_id:
        try:
            cat = Categoria.objects.get(id=categoria_id)
            cantidad = queryset.update(categoria=cat)
            modeladmin.message_user(
                request,
                f"¡Se actualizaron {cantidad} productos a la categoría '{cat.nombre}'!"
            )
        except Categoria.DoesNotExist:
            modeladmin.message_user(request, "La categoría seleccionada no existe.", level='error')
    else:
        modeladmin.message_user(
            request,
            "Advertencia: Debes seleccionar una categoría en el desplegable superior.",
            level='warning'
        )

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre']

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    # Añadimos 'mostrar_imagen' al inicio de la lista
    list_display = ['mostrar_imagen', 'nombre', 'categoria', 'precio_venta', 'stock']
    list_editable = ['precio_venta', 'stock']
    list_filter = ['categoria']
    search_fields = ['nombre', 'codigo']
    actions = [cambiar_categoria_lote]
    action_form = AsignarCategoriaForm

    # Método para renderizar la foto visualmente
    def mostrar_imagen(self, obj):
        if obj.imagen:
            return format_html('<img src="{}" style="width: 45px; height: 45px; object-fit: contain; border-radius: 4px; border: 1px solid #ddd;" />', obj.imagen.url)
        return format_html('<span style="color: #999; font-style: italic;">Sin foto</span>')
    
    mostrar_imagen.short_description = 'Imagen'
    


@admin.register(ZonaDomicilio)
class ZonaDomicilioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'tarifa_base', 'descuento_compra_grande', 'monto_minimo_descuento', 'activa')
    list_editable = ('tarifa_base', 'descuento_compra_grande', 'monto_minimo_descuento', 'activa')

class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 0
    can_delete = False
    readonly_fields = ('producto', 'nombre_producto', 'cantidad', 'precio_unitario', 'subtotal')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('numero', 'nombre_cliente', 'telefono', 'cliente_registrado', 'tipo_entrega', 'zona',
                    'subtotal', 'costo_envio', 'total', 'estado', 'fecha_creacion')
    list_display_links = ('numero', 'nombre_cliente')
    list_filter = ('estado', 'tipo_entrega', 'zona', 'fecha_creacion')
    list_editable = ('estado',)
    search_fields = ('nombre_cliente', 'telefono', 'usuario__username')
    date_hierarchy = 'fecha_creacion'
    ordering = ('-id',)
    readonly_fields = ('numero', 'usuario', 'fecha_creacion')
    inlines = [DetallePedidoInline]

    @admin.display(description='N.º pedido', ordering='id')
    def numero(self, obj):
        return obj.codigo

    @admin.display(description='Cuenta', boolean=True)
    def cliente_registrado(self, obj):
        return obj.usuario_id is not None


@admin.register(PerfilCliente)
class PerfilClienteAdmin(admin.ModelAdmin):
    list_display = ('user', 'telefono', 'direccion')
    search_fields = ('user__username', 'user__first_name', 'user__email', 'telefono')
