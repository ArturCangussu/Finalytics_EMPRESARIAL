from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('analisador.urls')), # Esta linha direciona tudo para o seu app
    path('contas/', include('django.contrib.auth.urls')),
]
