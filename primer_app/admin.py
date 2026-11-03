from django.contrib import admin
from django.contrib.admin.helpers import ActionForm
from django import forms
from .models import Categoria, Producto

# 1. Creamos un formulario en la acción para elegir a qué categoría se van a mover
class AsignarCategoriaForm(ActionForm):
    nueva_categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(), 
        required=False, 
        label="Categoría destino"
    )

# 2. Creamos la acción en lote que lee la categoría seleccionada en el formulario
@admin.action(description='Cambiar categoría a los productos seleccionados')
def cambiar_categoria_lote(modeladmin, request, queryset):
    categoria_id = request.POST.get('nueva_categoria')
    
    if categoria_id:
        try:
            cat = Categoria.objects.get(id=categoria_id)
            cantidad = queryset.update(categoria=cat)
            modeladmin.message_user(
                request, 
                f"¡Se actualizaron {cantidad} productos a la categoría '{cat.nombre}' con éxito!"
            )
        except Categoria.DoesNotExist:
            modeladmin.message_user(request, "La categoría seleccionada no es válida.", level='error')
    else:
        modeladmin.message_user(
            request, 
            "Advertencia: Debes seleccionar una categoría en el menú desplegable de al lado antes de presionar 'Ir'.", 
            level='warning'
        )

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre']

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'categoria', 'precio_venta', 'stock']
    list_editable = ['precio_venta', 'stock']
    list_filter = ['categoria']
    search_fields = ['nombre']
    actions = [cambiar_categoria_lote]
    action_form = AsignarCategoriaForm  # <--- Vinculamos el selector de categorías aquí