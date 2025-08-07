from django.urls import path
from . import views

urlpatterns = [
    path('', views.pagina_inicial, name='home'),
    path('regras/', views.gerenciar_regras, name='gerenciar_regras'),
    path('historico/', views.historico_extratos, name='historico'),
    path('comparar/', views.comparar_extratos, name='comparar'),
    path('relatorio/<int:extrato_id>/', views.pagina_relatorio, name='pagina_relatorio'),
    path('relatorio/<int:extrato_id>/reprocessar/', views.reprocessar_relatorio, name='reprocessar_relatorio'),
    path('relatorio/<int:extrato_id>/categoria/<str:nome_categoria>/', views.detalhe_categoria, name='detalhe_categoria'),
    path('regras/criar-rapido/', views.criar_regra_rapida, name='criar_regra_rapida'),
    path('historico/apagar/<int:extrato_id>/', views.apagar_extrato, name='apagar_extrato'),
    path('regras/editar/<int:regra_id>/', views.editar_regra, name='editar_regra'),
    path('regras/apagar/<int:regra_id>/', views.apagar_regra, name='apagar_regra'),
    path('transacao/editar/<int:transacao_id>/', views.editar_transacao, name='editar_transacao'),
    path('cadastro/', views.cadastro_usuario, name='cadastro'),
]
