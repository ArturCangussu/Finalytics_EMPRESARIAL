from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required 
from .motor_analise import processar_extrato
from .models import Regra, Transacao, Extrato, RelatorioConciliacao
import pandas as pd
from django.urls import reverse
from django.contrib import messages # Importa o sistema de mensagens do Django
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .motor_analise import (
    _processar_formato_sicoob_html,
    _processar_formato_caixa,
    _processar_formato_sicoob,
    _processar_relatorio_seu_condominio_csv,
    conciliar_dataframes
)
import datetime
import numpy as np
from django.utils.text import capfirst


PALAVRAS_DESTAQUE = [
    "taxa de condomínio", "taxas de condomínio", "arrec extra", "juros por atraso",
    "multa por atraso", "consumo de gás", "(-) tarifas de recebimentos",
    "(-) descontos nas cobranças", "fundo de reserva", "fundo reserva", "tar pix", "TAXA DE CONDOMÍNIO JUNHO/2025"
]


def marcar_destaques(lista_transacoes, campo_descricao):
    """
    Percorre uma lista de transações e retorna uma NOVA LISTA com a chave 'destaque' adicionada.
    """
    nova_lista = []
    if lista_transacoes: # Garante que a lista não está vazia
        for transacao_original in lista_transacoes:
            transacao_nova = transacao_original.copy() # Cria uma cópia do dicionário
            descricao = transacao_nova.get(campo_descricao)
            transacao_nova['destaque'] = False
            if isinstance(descricao, str):
                desc_lower = descricao.lower().strip()
                if any(palavra in desc_lower for palavra in PALAVRAS_DESTAQUE):
                    transacao_nova['destaque'] = True
            nova_lista.append(transacao_nova)
    return nova_lista


@login_required
def pagina_inicial(request):
    # Lógica para o método GET (preenchimento dos dropdowns)
    if request.method == 'GET':
        hoje = datetime.date.today()
        ano_atual = hoje.year
        mes_atual = hoje.month
        lista_anos = list(range(ano_atual - 1, ano_atual + 4)) 
        contexto = {
            'active_page': 'home', 'ano_atual': ano_atual,
            'mes_atual': mes_atual, 'lista_anos': lista_anos
        }
        return render(request, 'analisador/pagina_inicial.html', contexto)

    # Lógica do POST (quando o formulário é enviado)
    if request.method == 'POST':
        arquivo_extrato = request.FILES.get('arquivo_extrato')
        arquivos_seu_condominio = request.FILES.getlist('arquivos_seu_condominio')
        mes_num_str = request.POST.get('mes_selecionado')
        ano_num_str = request.POST.get('ano_selecionado')

        # Recria o contexto base para o caso de erro, para não quebrar a página
        hoje = datetime.date.today()
        contexto_erro = {
            'active_page': 'home', 'ano_atual': hoje.year,
            'mes_atual': hoje.month, 'lista_anos': list(range(hoje.year - 1, hoje.year + 4))
        }

        if not arquivo_extrato or not arquivos_seu_condominio or not mes_num_str or not ano_num_str:
            messages.error(request, 'Por favor, envie todos os arquivos e selecione mês/ano.')
            return render(request, 'analisador/pagina_inicial.html', contexto_erro)
        
        try:
            mes_num = int(mes_num_str)
            ano_num = int(ano_num_str)

            mapa_meses_inverso = {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
                7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }
            nome_mes = mapa_meses_inverso.get(mes_num, '')
            mes_referencia = f"{capfirst(nome_mes)}/{ano_num}"

            print("Processando extrato do banco...")
            df_banco = None
            if arquivo_extrato.name.lower().endswith('.html'):
                df_banco_bruto = _processar_formato_sicoob_html(arquivo_extrato)
                df_banco = df_banco_bruto[['Data', 'Descricao', 'Valor', 'Topico']]
            else:
                df_com_skip = pd.read_excel(arquivo_extrato, skiprows=1)
                df_banco_bruto = None
                if 'Data Lançamento' in df_com_skip.columns and 'Valor Lançamento' in df_com_skip.columns:
                    df_banco_bruto = _processar_formato_caixa(df_com_skip)
                elif 'DATA' in df_com_skip.columns and 'HISTÓRICO' in df_com_skip.columns:
                    df_banco_bruto = _processar_formato_sicoob(df_com_skip)
                
                if df_banco_bruto is not None:
                    df_banco = df_banco_bruto[['Data', 'Descricao', 'Valor', 'Topico']]
                else:
                    raise ValueError("Formato de extrato bancário Excel não reconhecido.")

            if df_banco is not None and not df_banco.empty:
                df_banco['Data'] = pd.to_datetime(df_banco['Data'], errors='coerce')
                filtro_mes_ano = (df_banco['Data'].dt.month == mes_num) & (df_banco['Data'].dt.year == ano_num)
                
                transacoes_antes = len(df_banco)
                df_banco = df_banco[filtro_mes_ano].copy()
                transacoes_depois = len(df_banco)

                print(f"Filtro por mês/ano '{mes_referencia}' aplicado: {transacoes_antes} -> {transacoes_depois} transações.")
                
                # <<< MUDANÇA PRINCIPAL: Interrompe se não houver transações >>>
                if transacoes_depois == 0 and transacoes_antes > 0:
                    messages.warning(request, f"Atenção: Nenhuma transação foi encontrada no extrato para o mês de referência '{mes_referencia}'. Verifique se o arquivo e o mês selecionado estão corretos.")
                    # Recria o contexto para manter a seleção do usuário na página
                    contexto_retorno = {
                        'active_page': 'home',
                        'ano_atual': ano_num, # Devolve o ano que o usuário selecionou
                        'mes_atual': mes_num, # Devolve o mês que o usuário selecionou
                        'lista_anos': list(range(hoje.year - 1, hoje.year + 4))
                    }
                    return render(request, 'analisador/pagina_inicial.html', contexto_retorno)
            
            print(f"Processando {len(arquivos_seu_condominio)} relatório(s) 'Seu Condomínio'...")
            lista_de_dfs = [ _processar_relatorio_seu_condominio_csv(arquivo_csv) for arquivo_csv in arquivos_seu_condominio ]
            df_seu_condominio = pd.concat(lista_de_dfs, ignore_index=True)
            
            conciliadas, apenas_banco, apenas_relatorio = conciliar_dataframes(df_banco, df_seu_condominio)

            conciliadas = conciliadas.replace({np.nan: None})
            apenas_banco = apenas_banco.replace({np.nan: None})
            apenas_relatorio = apenas_relatorio.replace({np.nan: None})
            for df_resultado in [conciliadas, apenas_banco, apenas_relatorio]:
                if 'Data' in df_resultado.columns:
                    df_resultado['Data'] = pd.to_datetime(df_resultado['Data'], errors='coerce').dt.strftime('%Y-%m-%d')

            novo_relatorio = RelatorioConciliacao.objects.create(
                usuario=request.user, mes_referencia=mes_referencia,
                conciliadas=conciliadas.to_dict('records'),
                apenas_banco=apenas_banco.to_dict('records'),
                apenas_relatorio=apenas_relatorio.to_dict('records')
            )
            return redirect('ver_conciliacao', relatorio_id=novo_relatorio.id)

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f"Erro ao processar os arquivos: {e}")
            return render(request, 'analisador/pagina_inicial.html', contexto_erro)
    
    return redirect('home')

@login_required
def gerenciar_regras(request):
    extrato_id_origem = request.GET.get('from_report')

    if request.method == 'POST':
        nova_palavra = request.POST.get('palavra_chave')
        nova_categoria = request.POST.get('categoria')

        if nova_palavra and nova_categoria:
            Regra.objects.create(
                usuario=request.user,
                palavra_chave=nova_palavra,
                categoria=nova_categoria
            )
        
        if extrato_id_origem:
            return redirect(f"{reverse('gerenciar_regras')}?from_report={extrato_id_origem}")
        return redirect('gerenciar_regras')

    regras_do_usuario = Regra.objects.filter(usuario=request.user)
    contexto = {
        'regras': regras_do_usuario,
        'active_page': 'regras',
        'extrato_id_origem': extrato_id_origem
    }
    return render(request, 'analisador/gerenciar_regras.html', contexto)


@login_required
def detalhe_categoria(request, extrato_id, nome_categoria):
    extrato = Extrato.objects.get(id=extrato_id, usuario=request.user)
    transacoes = Transacao.objects.filter(
        extrato_id=extrato_id, 
        usuario=request.user, 
        subtopico=nome_categoria
    ).order_by('data')


    for t in transacoes:
        data_obj = pd.to_datetime(t.data, errors='coerce')
        
        if pd.notna(data_obj):
            t.data_formatada = data_obj.strftime('%d/%m/%Y')
        else:
            t.data_formatada = 'Data Inválida' 

    contexto = {
        'extrato': extrato,
        'nome_categoria': nome_categoria,
        'transacoes': transacoes 
    }
    return render(request, 'analisador/detalhe_categoria.html', contexto)


@login_required
def historico_extratos(request):
    extratos_antigos = Extrato.objects.filter(usuario=request.user)
    relatorios_novos = RelatorioConciliacao.objects.filter(usuario=request.user)
    
    contexto = {
        'extratos': extratos_antigos,
        'relatorios': relatorios_novos,
        'active_page': 'historico'
    }
    return render(request, 'analisador/historico.html', contexto)


@login_required
def pagina_relatorio(request, extrato_id):
    extrato = Extrato.objects.get(id=extrato_id, usuario=request.user)
    transacoes = Transacao.objects.filter(extrato=extrato)

    
    search_query = request.GET.get('q')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    # Se não houver transações, retorna um contexto vazio
    if not transacoes.exists():
        contexto_vazio = {
            'extrato': extrato, 'total_receitas': '0,00', 'total_despesas': '0,00', 'saldo_liquido': '0,00',
            'resumo_despesas': pd.DataFrame(), 'resumo_receitas': pd.DataFrame(), 'nao_categorizadas': pd.DataFrame(),
            'labels_grafico': [], 'dados_grafico': [], 'valor_total_despesas_detalhe': 0, 'valor_total_receitas_detalhe': 0,
            'labels_grafico_receitas': [], 'dados_grafico_receitas': []
        }
        return render(request, 'analisador/relatorio.html', contexto_vazio)

    # --- Início do processamento com Pandas ---
    df = pd.DataFrame(list(transacoes.values('data', 'descricao', 'valor', 'topico', 'subtopico', 'origem_descricao')))


    if not df.empty:
        df['data_dt'] = pd.to_datetime(df['data'], errors='coerce') # Coluna técnica para filtrar
        if search_query:
            df = df[df['descricao'].str.contains(search_query, case=False, na=False)]
        if data_inicio:
            df = df[df['data_dt'] >= pd.to_datetime(data_inicio)]
        if data_fim:
            df = df[df['data_dt'] <= pd.to_datetime(data_fim)]

    # Se o DataFrame ficou vazio após o filtro, trate como se não houvesse transações
    if df.empty:
        pass


    df['valor'] = pd.to_numeric(df['valor'], errors='coerce').fillna(0)
    df['Data'] = pd.to_datetime(df['data'], errors='coerce').dt.strftime('%d/%m/%Y')

    def limpar_descricao_para_exibicao(d):
        d_str = str(d or '')
        if ' - ' in d_str: return d_str.split(' - ')[-1].strip()
        return d_str
    df['DescricaoLimpa'] = df['descricao'].apply(limpar_descricao_para_exibicao)

    df = df.rename(columns={'subtopico': 'Subtópico', 'valor': 'Valor', 'topico': 'Tópico', 'DescricaoLimpa': 'Remetente_Destinatario'})
    
    df_receitas = df[df['Tópico'] == 'Receita']
    df_despesas = df[df['Tópico'] == 'Despesa']
    total_r, total_d = df_receitas['Valor'].sum(), df_despesas['Valor'].sum()
    saldo_l = total_r - total_d

    resumo_d_series = df_despesas.groupby('Subtópico')['Valor'].sum().sort_values(ascending=False)
    resumo_d = resumo_d_series.reset_index()
    resumo_r_series = df_receitas.groupby('Subtópico')['Valor'].sum().sort_values(ascending=False)
    resumo_r = resumo_r_series.reset_index()
    
    nao_cat_df = df[df['Subtópico'] == 'Não categorizado'].copy()
    colunas_desejadas = ['Tópico', 'Data', 'Remetente_Destinatario', 'Valor', 'origem_descricao']
    nao_cat = nao_cat_df.reindex(columns=colunas_desejadas).fillna('')
    
    # DADOS PARA GRÁFICO DE DESPESAS
    labels_grafico = list(resumo_d_series.index)
    dados_grafico = [float(valor) for valor in resumo_d_series.abs().values]
    
    # DADOS PARA GRÁFICO DE RECEITAS
    labels_grafico_receitas = list(resumo_r_series.index)
    dados_grafico_receitas = [float(valor) for valor in resumo_r_series.abs().values]
    
    contexto = {
        'extrato': extrato, 'total_receitas': f'{total_r:,.2f}', 'total_despesas': f'{abs(total_d):,.2f}', 'saldo_liquido': f'{saldo_l:,.2f}',
        'resumo_despesas': resumo_d, 'resumo_receitas': resumo_r, 'nao_categorizadas': nao_cat,
        'valor_total_despesas_detalhe': total_d, 'valor_total_receitas_detalhe': total_r,
        # Variáveis para os dois gráficos
        'labels_grafico': labels_grafico, 'dados_grafico': dados_grafico,
        'labels_grafico_receitas': labels_grafico_receitas, 'dados_grafico_receitas': dados_grafico_receitas,
        # Devolve os filtros para manter os campos preenchidos
        'search_query': search_query, 'data_inicio': data_inicio, 'data_fim': data_fim,
    }
    return render(request, 'analisador/relatorio.html', contexto)






@login_required
def comparar_extratos(request):
    if request.method == 'POST':
        ids_selecionados = request.POST.getlist('extratos_selecionados')
        
        if len(ids_selecionados) < 2:
            return redirect('comparar')

        transacoes_selecionadas = Transacao.objects.filter(extrato_id__in=ids_selecionados, usuario=request.user)
        df_transacoes = pd.DataFrame(list(transacoes_selecionadas.values('extrato__mes_referencia', 'subtopico', 'valor', 'topico')))
        
        df_transacoes = df_transacoes.rename(columns={'extrato__mes_referencia': 'mes_referencia'})
        df_despesas = df_transacoes[df_transacoes['topico'] == 'Despesa']

        if df_despesas.empty:
            tabela_comparativa = pd.DataFrame()
        else:
            tabela_comparativa = df_despesas.pivot_table(
                index='subtopico',
                columns='mes_referencia',
                values='valor',
                aggfunc='sum'
            ).fillna(0)
            tabela_comparativa = tabela_comparativa.rename_axis(index='Categoria', columns=None)
        
        tabela_html_formatada = tabela_comparativa.astype(float).to_html(
            classes='table table-striped',
            float_format=lambda x: f'R$ {x:,.2f}'
        )

        contexto = {
            'tabela_html': tabela_html_formatada
        }
        
        return render(request, 'analisador/relatorio_comparativo.html', contexto)

    extratos = Extrato.objects.filter(usuario=request.user).order_by('-data_upload')
    contexto = {
        'extratos': extratos,
        'active_page': 'comparar'
    }
    return render(request, 'analisador/comparar.html', contexto)

@login_required
def reprocessar_relatorio(request, extrato_id):
    regras_do_usuario = Regra.objects.filter(usuario=request.user)
    regras_de_categorizacao = { regra.palavra_chave: regra.categoria for regra in regras_do_usuario }

    def categorizar_transacao(descricao):
        if not isinstance(descricao, str): return 'Descrição Inválida'
        for palavra_chave, categoria in regras_de_categorizacao.items():
            if palavra_chave.lower() in descricao.lower():
                return categoria
        return 'Não categorizado'

    transacoes_para_atualizar = Transacao.objects.filter(extrato_id=extrato_id, usuario=request.user)

    for transacao in transacoes_para_atualizar:
        if not transacao.categorizacao_manual:
            transacao.subtopico = categorizar_transacao(transacao.descricao)
            transacao.save()

    messages.success(request, "O relatório foi reprocessado com sucesso!")
    return redirect('pagina_relatorio', extrato_id=extrato_id)

@login_required
def criar_regra_rapida(request):
    if request.method == 'POST':
        palavra_chave = request.POST.get('palavra_chave')
        categoria = request.POST.get('categoria')
        extrato_id = request.POST.get('extrato_id')

        if palavra_chave and categoria:
            Regra.objects.get_or_create(
                usuario=request.user,
                palavra_chave=palavra_chave,
                defaults={'categoria': categoria}
            )
        
        if extrato_id:
            return redirect('reprocessar_relatorio', extrato_id=extrato_id)

    return redirect('home')

@login_required
def apagar_extrato(request, extrato_id):
    if request.method == 'POST':
        extrato = Extrato.objects.get(id=extrato_id, usuario=request.user)
        extrato.delete()
    
    return redirect('historico')


@login_required
def editar_regra(request, regra_id):
    regra = Regra.objects.get(id=regra_id, usuario=request.user)

    if request.method == 'POST':
        # Pega os novos dados do formulário
        regra.palavra_chave = request.POST.get('palavra_chave')
        regra.categoria = request.POST.get('categoria')
        regra.save() # Salva as alterações
        return redirect('gerenciar_regras')

    contexto = {
        'regra': regra,
        'active_page': 'regras'
    }
    return render(request, 'analisador/editar_regra.html', contexto)


@login_required
def apagar_regra(request, regra_id):
    if request.method == 'POST':
        regra = Regra.objects.get(id=regra_id, usuario=request.user)
        regra.delete()
    return redirect('gerenciar_regras')



@login_required
def editar_transacao(request, transacao_id):
    transacao = Transacao.objects.get(id=transacao_id, usuario=request.user)

    if request.method == 'POST':
        transacao.descricao = request.POST.get('descricao')
        transacao.subtopico = request.POST.get('subtopico')

        transacao.categorizacao_manual = True

        transacao.save()
        return redirect('pagina_relatorio', extrato_id=transacao.extrato.id)

    contexto = {
        'transacao': transacao
    }
    return render(request, 'analisador/editar_transacao.html', contexto)





def cadastro_usuario(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario) # Loga o usuário automaticamente após o cadastro
            return redirect('home') # Redireciona para a página inicial
    else:
        form = UserCreationForm()
    
    contexto = {
        'form': form
    }
    return render(request, 'analisador/cadastro.html', contexto)


@login_required
def criar_regras_em_lote(request):
    if request.method == 'POST':
        palavras_chave = request.POST.getlist('palavras_chave_selecionadas')
        
        nova_categoria = request.POST.get('categoria_em_lote')
        
        extrato_id = request.POST.get('extrato_id')

        if palavras_chave and nova_categoria and extrato_id:
            # Para cada palavra-chave selecionada, cria uma nova regra
            for palavra in palavras_chave:
                Regra.objects.get_or_create(
                    usuario=request.user,
                    palavra_chave=palavra,
                    defaults={'categoria': nova_categoria}
                )
            
            messages.success(request, f'{len(palavras_chave)} regras foram criadas/atualizadas com a categoria "{nova_categoria}".')
            return redirect('reprocessar_relatorio', extrato_id=extrato_id)

    messages.error(request, 'Ocorreu um erro ao processar a solicitação.')
    return redirect('home')


@login_required
def ver_conciliacao(request, relatorio_id):
    """Exibe um relatório de conciliação salvo no banco de dados."""
    relatorio = RelatorioConciliacao.objects.get(id=relatorio_id, usuario=request.user)

    conciliadas_originais = relatorio.conciliadas
    apenas_banco_originais = relatorio.apenas_banco
    apenas_relatorio_originais = relatorio.apenas_relatorio


    lista_conciliadas = marcar_destaques(conciliadas_originais, 'Descricao_relatorio')
    lista_apenas_relatorio = marcar_destaques(apenas_relatorio_originais, 'Descricao_relatorio')
    

    lista_apenas_banco = apenas_banco_originais


    transacoes_apuradas = lista_conciliadas + lista_apenas_banco
    total_receitas_apuradas = 0
    total_despesas_apuradas = 0
    total_tarifas_pix = 0

    if transacoes_apuradas:
        df_apurado = pd.DataFrame(transacoes_apuradas)
        somas_por_tipo = df_apurado.groupby('Tipo')['Valor'].sum()
        total_receitas_apuradas = somas_por_tipo.get('Receita', 0)
        total_despesas_apuradas = somas_por_tipo.get('Despesa', 0)
        
        despesas_df = df_apurado[df_apurado['Tipo'] == 'Despesa']
        if 'Descricao_banco' in despesas_df.columns:
            tarifas_df = despesas_df[despesas_df['Descricao_banco'].str.upper().str.contains('TAR PIX', na=False)]
            total_tarifas_pix = tarifas_df['Valor'].sum()


    for item in lista_apenas_banco: item['Data'] = pd.to_datetime(item['Data'])
    for item in lista_apenas_relatorio: item['Data'] = pd.to_datetime(item['Data'])
    for item in lista_conciliadas: item['Data'] = pd.to_datetime(item['Data'])
        
    
    contexto = {
        'conciliadas': lista_conciliadas,
        'apenas_banco': lista_apenas_banco,
        'apenas_relatorio': lista_apenas_relatorio,
        'total_receitas_apuradas': f'R$ {total_receitas_apuradas:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
        'total_despesas_apuradas': f'R$ {total_despesas_apuradas:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
        'total_tarifas_pix': f'R$ {total_tarifas_pix:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
        'active_page': 'home',
    }
    return render(request, 'analisador/relatorio.html', contexto)




@login_required
def apagar_conciliacao(request, relatorio_id):
    if request.method == 'POST':

        try:
            relatorio = RelatorioConciliacao.objects.get(id=relatorio_id, usuario=request.user)
            relatorio.delete()
            messages.success(request, "Relatório de conciliação apagado com sucesso!")
        except RelatorioConciliacao.DoesNotExist:
            messages.error(request, "Relatório não encontrado ou você não tem permissão para apagá-lo.")
    
    return redirect('historico')