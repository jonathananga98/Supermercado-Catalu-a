from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from . import views, api_views
from django.conf.urls.static import static

urlpatterns = [
    path('', views.lista_productos, name='lista_productos'),
    path('registro/', views.registro_usuario, name='registro'),
    path('login/', views.iniciar_sesion, name='login'),
    path('logout/', views.cerrar_sesion, name='logout'),
    path('carrito/', views.ver_carrito, name='ver_carrito'),
    path('agregar/<int:producto_id>/', views.agregar_carrito, name='agregar_carrito'),
    path('restar/<int:producto_id>/', views.restar_carrito, name='restar_carrito'),
    path('eliminar/<int:producto_id>/', views.eliminar_carrito, name='eliminar_carrito'),
    path('checkout/', views.procesar_pedido, name='procesar_pedido'),
    path('api/productos/', views.api_lista_productos, name='api_lista_productos'),
    path('api/carrito/agregar/<int:producto_id>/', views.api_agregar_carrito, name='api_agregar_carrito'),
    path('api/carrito/actualizar/<int:producto_id>/', views.api_actualizar_carrito, name='api_actualizar_carrito'), 
    path('api/zonas/', views.api_zonas_domicilio, name='api_zonas_domicilio'),
    # Pedidos (invitado o autenticado) y cuentas de clientes
    path('api/pedidos/', api_views.crear_pedido, name='api_crear_pedido'),
    path('api/checkout/', api_views.crear_pedido, name='api_checkout'),  # alias retrocompatible
    path('api/auth/registro/', api_views.registro_cliente, name='api_registro'),
    path('api/auth/login/', api_views.login_cliente, name='api_login'),
    path('api/auth/perfil/', api_views.perfil_cliente, name='api_perfil'),
    path('api/auth/logout/', api_views.logout_cliente, name='api_logout'),

]


