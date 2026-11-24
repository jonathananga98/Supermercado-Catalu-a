from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Categoria, DetallePedido, Pedido, PerfilCliente, Producto, ZonaDomicilio


class BaseApiTest(TestCase):
    def setUp(self):
        cache.clear()  # reinicia los throttles entre pruebas
        self.client = APIClient()
        cat = Categoria.objects.create(nombre='ABARROTES')
        self.arroz = Producto.objects.create(nombre='Arroz 500g', precio_venta=Decimal('3000'), stock=10, categoria=cat)
        self.leche = Producto.objects.create(nombre='Leche 1L', precio_venta=Decimal('4500'), stock=2, categoria=cat)
        self.zona = ZonaDomicilio.objects.create(
            nombre='Zona 1', tarifa_base=Decimal('3500'),
            descuento_compra_grande=Decimal('1000'), monto_minimo_descuento=Decimal('90000'),
        )

    def payload(self, **extra):
        data = {
            'nombre': 'Juan Pérez', 'telefono': '310 123 4567', 'tipo_entrega': 'domicilio',
            'zona_id': self.zona.id, 'direccion': 'Calle 45 # 12-34', 'metodo_pago': 'Efectivo al recibir',
            'items': [{'id': self.arroz.id, 'cantidad': 3}, {'id': self.leche.id, 'cantidad': 1}],
        }
        data.update(extra)
        return data


class PedidosTests(BaseApiTest):
    def test_invitado_crea_pedido_y_descuenta_stock(self):
        r = self.client.post('/api/pedidos/', self.payload(), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        pedido = Pedido.objects.get(pk=r.data['pedido_id'])
        self.assertEqual(r.data['codigo'], f'CAT-{pedido.id:05d}')
        self.assertIsNone(pedido.usuario)
        self.assertEqual(pedido.subtotal, Decimal('13500'))
        self.assertEqual(pedido.costo_envio, Decimal('3500'))
        self.assertEqual(pedido.total, Decimal('17000'))
        self.assertEqual(pedido.detalles.count(), 2)
        self.arroz.refresh_from_db(); self.leche.refresh_from_db()
        self.assertEqual((self.arroz.stock, self.leche.stock), (7, 1))
        self.assertIn(pedido.codigo, r.data['mensaje_whatsapp'])
        self.assertTrue(r.data['url_whatsapp'].startswith('https://wa.me/573202656464?text='))

    def test_stock_insuficiente_no_guarda_nada(self):
        items = [{'id': self.arroz.id, 'cantidad': 2}, {'id': self.leche.id, 'cantidad': 5}]
        r = self.client.post('/api/pedidos/', self.payload(items=items), format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['disponible'], 2)
        self.assertEqual(Pedido.objects.count(), 0)
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.stock, 10)  # el arroz tampoco se descontó (rollback)

    def test_lineas_repetidas_se_suman_para_validar_stock(self):
        items = [{'id': self.leche.id, 'cantidad': 2}, {'id': self.leche.id, 'cantidad': 1}]
        r = self.client.post('/api/pedidos/', self.payload(items=items), format='json')
        self.assertEqual(r.status_code, 409)

    def test_descuento_domicilio_por_compra_grande(self):
        items = [{'id': self.arroz.id, 'cantidad': 10}]
        self.arroz.precio_venta = Decimal('9000'); self.arroz.save()
        r = self.client.post('/api/pedidos/', self.payload(items=items), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['costo_envio'], 2500.0)  # 3500 - 1000

    def test_recoger_sin_envio_ni_direccion(self):
        r = self.client.post('/api/pedidos/', self.payload(tipo_entrega='recoger', direccion='', zona_id=None), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['costo_envio'], 0)

    def test_domicilio_exige_direccion(self):
        r = self.client.post('/api/pedidos/', self.payload(direccion=''), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('dirección', r.data['error'].lower())

    def test_carrito_vacio_o_cantidad_invalida(self):
        self.assertEqual(self.client.post('/api/pedidos/', self.payload(items=[]), format='json').status_code, 400)
        r = self.client.post('/api/pedidos/', self.payload(items=[{'id': self.arroz.id, 'cantidad': 0}]), format='json')
        self.assertEqual(r.status_code, 400)

    def test_producto_inexistente(self):
        r = self.client.post('/api/pedidos/', self.payload(items=[{'id': 99999, 'cantidad': 1}]), format='json')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_usuario_autenticado_queda_asociado_y_guarda_direccion(self):
        user = User.objects.create_user('3109998888', password='secreto1', first_name='Ana')
        PerfilCliente.objects.create(user=user, telefono='3109998888')
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        r = self.client.post('/api/pedidos/', self.payload(), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Pedido.objects.get(pk=r.data['pedido_id']).usuario, user)
        user.perfil.refresh_from_db()
        self.assertEqual(user.perfil.direccion, 'Calle 45 # 12-34')

    def test_token_invalido_se_trata_como_invitado(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token basura')
        r = self.client.post('/api/pedidos/', self.payload(), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(Pedido.objects.get(pk=r.data['pedido_id']).usuario)

    def test_crear_cuenta_desde_checkout(self):
        r = self.client.post('/api/pedidos/', self.payload(crear_cuenta=True, password='clave123'), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data['cuenta']['creada'])
        self.assertIn('token', r.data['sesion'])
        user = User.objects.get(username='3101234567')
        self.assertEqual(Pedido.objects.get(pk=r.data['pedido_id']).usuario, user)
        # puede entrar luego con teléfono formateado distinto
        login = APIClient().post('/api/auth/login/', {'identificador': '+57 310-123-4567', 'password': 'clave123'}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_crear_cuenta_con_telefono_existente_no_pierde_el_pedido(self):
        User.objects.create_user('3101234567', password='otra-clave')
        r = self.client.post('/api/pedidos/', self.payload(crear_cuenta=True, password='clave123'), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.data['cuenta']['creada'])
        self.assertNotIn('sesion', r.data)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_password_corta_al_crear_cuenta_rechaza_antes_de_guardar(self):
        r = self.client.post('/api/pedidos/', self.payload(crear_cuenta=True, password='123'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.stock, 10)

    def test_cancelar_pedido_devuelve_stock(self):
        r = self.client.post('/api/pedidos/', self.payload(), format='json')
        pedido = Pedido.objects.get(pk=r.data['pedido_id'])
        pedido.estado = 'CANCELADO'; pedido.save()
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.stock, 10)

    def test_alias_checkout_sigue_funcionando(self):
        self.assertEqual(self.client.post('/api/checkout/', self.payload(), format='json').status_code, 201)


class AuthTests(BaseApiTest):
    def registro(self, **extra):
        data = {'nombre': 'María Gómez', 'telefono': '320 555 1212', 'password': 'secreto1'}
        data.update(extra)
        return self.client.post('/api/auth/registro/', data, format='json')

    def test_registro_con_telefono(self):
        r = self.registro()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['usuario']['nombre'], 'María Gómez')
        self.assertEqual(r.data['usuario']['telefono'], '3205551212')
        self.assertTrue(Token.objects.filter(key=r.data['token']).exists())

    def test_registro_con_correo_solamente(self):
        r = self.registro(telefono='', email='Maria@Correo.com')
        self.assertEqual(r.status_code, 201, r.data)
        login = self.client.post('/api/auth/login/', {'identificador': 'maria@correo.com', 'password': 'secreto1'}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_registro_duplicado(self):
        self.registro()
        self.assertEqual(self.registro().status_code, 409)

    def test_registro_valida_datos(self):
        self.assertEqual(self.registro(password='123').status_code, 400)
        self.assertEqual(self.registro(telefono='', email='').status_code, 400)
        self.assertEqual(self.registro(telefono='12').status_code, 400)

    def test_login_ok_y_fallido(self):
        self.registro()
        ok = self.client.post('/api/auth/login/', {'identificador': '3205551212', 'password': 'secreto1'}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertIn('token', ok.data)
        mal = self.client.post('/api/auth/login/', {'identificador': '3205551212', 'password': 'nope'}, format='json')
        self.assertEqual(mal.status_code, 401)
        inexistente = self.client.post('/api/auth/login/', {'identificador': '3000000000', 'password': 'x'}, format='json')
        self.assertEqual(inexistente.status_code, 401)

    def test_perfil_y_logout(self):
        token = self.registro().data['token']
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(c.get('/api/auth/perfil/').data['usuario']['nombre'], 'María Gómez')
        self.assertEqual(c.post('/api/auth/logout/').status_code, 204)
        self.assertEqual(c.get('/api/auth/perfil/').status_code, 401)

    def test_cors_permite_angular(self):
        r = self.client.options('/api/pedidos/', HTTP_ORIGIN='http://localhost:4200',
                                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                                HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type')
        self.assertEqual(r.headers.get('access-control-allow-origin'), 'http://localhost:4200')
        self.assertIn('authorization', r.headers.get('access-control-allow-headers', ''))
