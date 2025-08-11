from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required 
from .motor_analise import processar_extrato
from .models import Regra, Transacao, Extrato
import pandas as pd
from django.urls import reverse
from django.contrib import messages # Importa o sistema de mensagens do Django
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

@login_required
def pagina_inicial(request):
    contexto = {'active_page': 'home'}

    if request.method == 'POST':
        arquivo_extrato = request.FILES.get('arquivo_extrato')
        mes_referencia = request.POST.get('mes_referencia')

        if not arquivo_extrato or not mes_referencia:
            messages.error(request, 'Por favor, preencha todos os campos.')
            return render(request, 'analisador/pagina_inicial.html', contexto)
        
        # --- VALIDAÇÃO DO TIPO DE ARQUIVO ---
        # Verifica se o nome do arquivo termina com .xlsx
        if not (arquivo_extrato.name.lower().endswith('.xlsx') or arquivo_extrato.name.lower().endswith('.html')):
            messages.error(request, 'Erro: O arquivo do extrato deve ser no formato .xlsx.')
            return render(request, 'analisador/pagina_inicial.html', contexto)
        # --- FIM DA VALIDAÇÃO ---

        novo_extrato = Extrato.objects.create(
            usuario=request.user,
            mes_referencia=mes_referencia
        )
        processar_extrato(arquivo_extrato, request.user, novo_extrato)
        
        return redirect('pagina_relatorio', extrato_id=novo_extrato.id)
    
    return render(request, 'analisador/pagina_inicial.html', contexto)


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

    # =======================================================================
    # ================ LÓGICA DE FORMATAÇÃO DE DATA ADICIONADA ===============
    # =======================================================================
    # Para cada transação, criamos um novo atributo com a data já formatada
    for t in transacoes:
        # Usamos o 'pd.to_datetime' que é robusto para converter os dados
        data_obj = pd.to_datetime(t.data, errors='coerce')
        
        # Verificamos se a data é válida antes de formatar
        if pd.notna(data_obj):
            t.data_formatada = data_obj.strftime('%d/%m/%Y')
        else:
            t.data_formatada = 'Data Inválida' # Ou pode deixar em branco: ''
    # =======================================================================

    contexto = {
        'extrato': extrato,
        'nome_categoria': nome_categoria,
        'transacoes': transacoes # A lista de transações agora tem o novo atributo
    }
    return render(request, 'analisador/detalhe_categoria.html', contexto)


@login_required
def historico_extratos(request):
    extratos = Extrato.objects.filter(usuario=request.user).order_by('-data_upload')
    contexto = {
        'extratos': extratos,
        'active_page': 'historico'
    }
    return render(request, 'analisador/historico.html', contexto)


@login_required
def pagina_relatorio(request, extrato_id):
    extrato = Extrato.objects.get(id=extrato_id, usuario=request.user)
    transacoes = Transacao.objects.filter(extrato=extrato)

    if not transacoes.exists():
        contexto = { 'extrato': extrato, 'total_receitas': '0,00', 'total_despesas': '0,00', 'saldo_liquido': '0,00', 'resumo_despesas': pd.DataFrame(), 'resumo_receitas': pd.DataFrame(), 'nao_categorizadas': pd.DataFrame(), 'labels_grafico': [], 'dados_grafico': [], 'valor_total_despesas_detalhe': 0, 'valor_total_receitas_detalhe': 0 }
        return render(request, 'analisador/relatorio.html', contexto)

    df = pd.DataFrame(list(transacoes.values('data', 'descricao', 'valor', 'topico', 'subtopico', 'origem_descricao')))
    df['valor'] = pd.to_numeric(df['valor'], errors='coerce').fillna(0)
    
    df['Data'] = pd.to_datetime(df['data'], errors='coerce').dt.strftime('%d/%m/%Y')
    
    def limpar_descricao_para_exibicao(d):
        d_str = str(d or '')
        if ' - ' in d_str:
            return d_str.split(' - ')[-1].strip()
        return d_str
    
    df['DescricaoLimpa'] = df['descricao'].apply(limpar_descricao_para_exibicao)

    df = df.rename(columns={ 'subtopico': 'Subtópico', 'valor': 'Valor', 'topico': 'Tópico', 'DescricaoLimpa': 'Remetente_Destinatario' })
    
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
    
    labels_grafico = list(resumo_d_series.index)
    dados_grafico = [float(valor) for valor in resumo_d_series.abs().values]
    
    contexto = {
        'extrato': extrato, 'total_receitas': f'{total_r:,.2f}', 'total_despesas': f'{abs(total_d):,.2f}', 'saldo_liquido': f'{saldo_l:,.2f}',
        'resumo_despesas': resumo_d, 'resumo_receitas': resumo_r, 'nao_categorizadas': nao_cat,
        'labels_grafico': labels_grafico, 'dados_grafico': dados_grafico,
        'valor_total_despesas_detalhe': total_d, 'valor_total_receitas_detalhe': total_r,
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
    # ... (a preparação das regras continua a mesma)
    regras_do_usuario = Regra.objects.filter(usuario=request.user)
    regras_de_categorizacao = { regra.palavra_chave: regra.categoria for regra in regras_do_usuario }

    def categorizar_transacao(descricao):
        # ... (a função de categorizar continua a mesma)
        if not isinstance(descricao, str): return 'Descrição Inválida'
        for palavra_chave, categoria in regras_de_categorizacao.items():
            if palavra_chave.lower() in descricao.lower():
                return categoria
        return 'Não categorizado'

    transacoes_para_atualizar = Transacao.objects.filter(extrato_id=extrato_id, usuario=request.user)

    for transacao in transacoes_para_atualizar:
        # SÓ REPROCESSA SE A TRANSAÇÃO NÃO ESTIVER "TRAVADA"
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
    # Busca a regra específica, garantindo que pertence ao usuário
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

        # ATIVA A "TRAVA"
        transacao.categorizacao_manual = True

        transacao.save()
        # Redireciona de volta para o relatório do extrato original
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
        # Pega a lista de todas as palavras-chave dos checkboxes que foram marcados
        palavras_chave = request.POST.getlist('palavras_chave_selecionadas')
        
        # Pega a categoria que o usuário digitou no campo de texto
        nova_categoria = request.POST.get('categoria_em_lote')
        
        extrato_id = request.POST.get('extrato_id')

        if palavras_chave and nova_categoria and extrato_id:
            # Para cada palavra-chave selecionada, cria uma nova regra
            for palavra in palavras_chave:
                # Usamos get_or_create para não criar regras duplicadas
                Regra.objects.get_or_create(
                    usuario=request.user,
                    palavra_chave=palavra,
                    defaults={'categoria': nova_categoria}
                )
            
            messages.success(request, f'{len(palavras_chave)} regras foram criadas/atualizadas com a categoria "{nova_categoria}".')
            # Redireciona para reprocessar o relatório e ver o resultado imediatamente
            return redirect('reprocessar_relatorio', extrato_id=extrato_id)

    # Se algo der errado, ou se não for POST, volta para a home
    messages.error(request, 'Ocorreu um erro ao processar a solicitação.')
    return redirect('home')