from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class TokenOpcional(TokenAuthentication):
    """
    TokenAuthentication "tolerante" para endpoints públicos (AllowAny).

    - Sin cabecera Authorization  -> invitado (AnonymousUser).
    - Token válido                -> request.user es el cliente.
    - Token inválido o vencido    -> se trata como invitado en lugar de fallar con 401,
      así un cliente con sesión caducada en el navegador puede seguir comprando.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None
