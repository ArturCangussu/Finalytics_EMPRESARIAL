# motor_analise.py (VERSÃO COM LIMPEZA INTELIGENTE DA DESCRIÇÃO)

import pandas as pd
import numpy as np
from .models import Regra, Transacao, Extrato
from bs4 import BeautifulSoup
import zipfile
import re
import io
from django.http import HttpResponse

def sanitize_excel_file(uploaded_file):
    """
    Repara um arquivo .xlsx malformado em memória, removendo atributos 'r' numéricos inválidos
    de células e linhas, que causam erros na biblioteca openpyxl.
    """
    print("--- INICIANDO SANITIZAÇÃO DO ARQUIVO EXCEL ---")
    
    # Usa um buffer de bytes para manipular o arquivo em memória
    sanitized_file_in_memory = io.BytesIO()

    # Cria um novo arquivo ZIP (o .xlsx sanitizado) em memória
    with zipfile.ZipFile(sanitized_file_in_memory, 'w', zipfile.ZIP_DEFLATED) as z_out:
        # Abre o arquivo original enviado pelo usuário como um ZIP
        with zipfile.ZipFile(uploaded_file, 'r') as z_in:
            # Itera sobre todos os arquivos internos do .xlsx original
            for item in z_in.infolist():
                content = z_in.read(item.filename)
                
                # Se for um arquivo de planilha (onde o erro ocorre), nós o tratamos
                if item.filename.startswith('xl/worksheets/sheet'):
                    print(f"DEBUG: Sanitizando a planilha: {item.filename}")
                    xml_content_str = content.decode('utf-8')
                    
                    # Regex para encontrar e REMOVER os atributos r="<somente_numeros>"
                    # Isso corrige o problema que você identificou!
                    sanitized_xml_content = re.sub(r' r="\d+"', '', xml_content_str)
                    
                    if xml_content_str != sanitized_xml_content:
                        print("DEBUG: Sanitização aplicada. Atributos 'r' inválidos foram removidos.")
                    else:
                        print("DEBUG: Nenhum atributo 'r' inválido encontrado para remover.")

                    # Escreve o conteúdo XML modificado no novo arquivo ZIP
                    z_out.writestr(item, sanitized_xml_content.encode('utf-8'))
                else:
                    # Para todos os outros arquivos (estilos, etc.), apenas copiamos
                    z_out.writestr(item, content)

    # "Rebobina" o arquivo em memória para que o Pandas possa lê-lo do início
    sanitized_file_in_memory.seek(0)
    print("--- SANITIZAÇÃO CONCLUÍDA ---")
    return sanitized_file_in_memory



def converter_data_robusta(data):
    if isinstance(data, (pd.Timestamp, np.datetime64)): return data
    try: return pd.to_datetime(data, unit='D', origin='1899-12-30')
    except (ValueError, TypeError): return pd.to_datetime(data, dayfirst=True, errors='coerce')

def _processar_formato_sicoob_html(arquivo_html):
    print("--- INICIANDO PROCESSAMENTO SICOOB HTML (COM LIMPEZA DE DESCRIÇÃO) ---")
    try:
        conteudo = arquivo_html.read().decode('latin-1', errors='ignore')
        soup = BeautifulSoup(conteudo, 'html.parser')
        
        tabela_lancamentos = None
        all_tables = soup.find_all('table')
        for table in all_tables:
            header = table.find('th', string=lambda t: t and 'DOCUMENTO' in t.upper())
            if header:
                tabela_lancamentos = table
                print("DEBUG: Tabela de lançamentos encontrada.")
                break
        
        if not tabela_lancamentos:
            raise ValueError("Nenhuma tabela de lançamentos com o cabeçalho 'DOCUMENTO' foi encontrada.")

        dados = []
        tbody = tabela_lancamentos.find('tbody')
        if not tbody:
            raise ValueError("Corpo da tabela (tbody) não encontrado.")
            
        for i, linha_tr in enumerate(tbody.find_all('tr')):
            # Desta vez, pegamos as células como objetos para analisar a descrição
            celulas_obj = linha_tr.find_all('td')
            
            # Validação primária (mesma de antes)
            if len(celulas_obj) == 4 and celulas_obj[0].get_text().strip() and "SALDO" not in celulas_obj[2].get_text().upper():
                
                data = celulas_obj[0].get_text().strip()
                documento = celulas_obj[1].get_text().strip()
                
                # ==============================================================================
                # === NOVA LÓGICA PARA EXTRAIR APENAS A ÚLTIMA LINHA DA DESCRIÇÃO ===
                # ==============================================================================
                descricao_cell = celulas_obj[2]
                # Pega todo o texto, usando '\n' como separador para manter as linhas
                texto_completo_com_linhas = descricao_cell.get_text(separator='\n').strip()
                # Divide o texto em uma lista de linhas e remove as que estiverem vazias
                linhas = [linha.strip() for linha in texto_completo_com_linhas.split('\n') if linha.strip()]
                
                descricao_final = ' '.join(linhas) # Um fallback caso a lógica falhe
                if linhas:
                    # Pega a última linha da lista como a descrição principal
                    descricao_final = linhas[-1]
                # ==============================================================================

                valor_str = celulas_obj[3].get_text().strip()

                # Lógica para extrair C/D do valor (mesma de antes)
                lancamento = ''
                valor_limpo = '0'
                if valor_str and valor_str[-1] in ['C', 'D']:
                    lancamento = valor_str[-1]
                    valor_limpo = valor_str[:-1].strip()
                
                print(f"DEBUG: Linha #{i+1} -> VÁLIDA. Descrição limpa: '{descricao_final}'")
                dados.append([data, documento, descricao_final, valor_limpo, lancamento])
            else:
                print(f"DEBUG: Linha #{i+1} -> IGNORADA (não é transação).")


        if not dados:
            raise ValueError("Nenhuma linha de transação válida foi encontrada na tabela após a análise.")

        print(f"--- PROCESSAMENTO CONCLUÍDO. Total de transações válidas: {len(dados)} ---")
        colunas = ['Data', 'Documento', 'Descricao', 'Valor', 'Lancamento']
        df = pd.DataFrame(dados, columns=colunas)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ValueError(f"Não foi possível processar o arquivo HTML com BeautifulSoup. Erro: {e}")
    
    # O restante do processamento para padronizar o DataFrame continua igual
    df_padronizado = df
    df_padronizado['Topico'] = np.where(df_padronizado['Lancamento'] == 'C', 'Receita', 'Despesa')
    
    df_padronizado['Valor'] = pd.to_numeric(
        df_padronizado['Valor'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0).abs()
    
    df_padronizado['origem_descricao'] = 'Historico'
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)
    
    return df_padronizado

# --- O RESTANTE DO ARQUIVO PERMANECE IGUAL ---

def _processar_formato_caixa(df):
    print("Formato Caixa Federal detectado.")
    # ... (código inalterado) ...
    df['origem_descricao'] = np.where(df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True).isna(), 'Historico', 'Nome/Razao Social')
    df['Nome/Razão Social'] = df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True)
    df['Nome/Razão Social'] = df['Nome/Razão Social'].fillna(df['Histórico'])
    df_padronizado = df.rename(columns={'Valor Lançamento': 'Valor', 'Nome/Razão Social': 'Descricao', 'Data Lançamento': 'Data'})
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'] < 0, 'Despesa', 'Receita')
    df_padronizado['Valor'] = df_padronizado['Valor'].abs()
    return df_padronizado

def _processar_formato_sicoob(df):
    print("Formato Sicoob XLSX detectado.")
    # ... (código inalterado) ...
    df['origem_descricao'] = 'Historico'
    df_padronizado = df.rename(columns={'HISTÓRICO': 'Descricao', 'VALOR': 'Valor', 'DATA': 'Data'})
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)
    df_padronizado['Valor'] = df_padronizado['Valor'].astype(str)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'].str.contains('C', na=False), 'Receita', 'Despesa')
    df_padronizado['Valor'] = df_padronizado['Valor'].str.replace('C', '', regex=False).str.replace('D', '', regex=False).str.strip()
    df_padronizado['Valor'] = df_padronizado['Valor'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    return df_padronizado

def processar_extrato(arquivo_extrato, usuario_logado, extrato_obj):
    # ... (código inalterado) ...
    if arquivo_extrato.name.lower().endswith('.html'):
        df_processado = _processar_formato_sicoob_html(arquivo_extrato)
    else:
        try:
            df_normal = pd.read_excel(arquivo_extrato)
            df_com_skip = pd.read_excel(arquivo_extrato, skiprows=1)
        except Exception as e:
            raise ValueError(f"Não foi possível ler o ficheiro Excel. Erro: {e}")
        if 'Data Lançamento' in df_com_skip.columns and 'Valor Lançamento' in df_com_skip.columns:
            df_processado = _processar_formato_caixa(df_com_skip)
        elif 'DATA' in df_com_skip.columns and 'HISTÓRICO' in df_com_skip.columns:
            df_processado = _processar_formato_sicoob(df_com_skip)
        else:
            print("Colunas encontradas (tentativa 1):", df_normal.columns)
            print("Colunas encontradas (tentativa 2):", df_com_skip.columns)
            raise ValueError("Formato de extrato não reconhecido.")

    df_processado.dropna(subset=['Data', 'Descricao'], how='all', inplace=True)
    regras_do_usuario = Regra.objects.filter(usuario=usuario_logado)
    regras_de_categorizacao = {regra.palavra_chave: regra.categoria for regra in regras_do_usuario}
    def categorizar_transacao(descricao):
        if not isinstance(descricao, str): return 'Não categorizado'
        for palavra_chave, categoria in regras_de_categorizacao.items():
            if palavra_chave.lower() in descricao.lower(): return categoria
        return 'Não categorizado'
    df_processado['Descricao'] = df_processado['Descricao'].fillna('').astype(str)
    df_processado['Subtopico'] = df_processado['Descricao'].apply(categorizar_transacao)
    Transacao.objects.filter(extrato=extrato_obj).delete()
    for index, linha in df_processado.iterrows():
        Transacao.objects.create(
            extrato=extrato_obj, usuario=usuario_logado, data=linha.get('Data', None),
            descricao=linha.get('Descricao', ''), valor=linha.get('Valor', 0.0),
            topico=linha.get('Topico', ''), subtopico=linha.get('Subtopico', ''),
            origem_descricao=linha.get('origem_descricao', '')
        )
    df_receitas = df_processado.loc[df_processado['Topico'] == 'Receita'].copy()
    df_despesas = df_processado.loc[df_processado['Topico'] == 'Despesa'].copy()
    total_despesas = df_despesas['Valor'].sum()
    total_receitas = df_receitas['Valor'].sum()
    saldo_liquido = total_receitas - total_despesas
    resumo_despesas = df_despesas.groupby('Subtopico')['Valor'].sum().sort_values(ascending=False)
    resumo_receitas = df_receitas.groupby('Subtopico')['Valor'].sum().sort_values(ascending=False)
    nao_categorizadas_bruto = df_processado.loc[df_processado['Subtopico'] == 'Não categorizado'].copy()
    colunas_desejadas = ['Topico', 'Data', 'Descricao', 'Valor', 'origem_descricao']
    nao_categorizadas_limpo = nao_categorizadas_bruto.reindex(columns=colunas_desejadas)
    return total_receitas, total_despesas, saldo_liquido, resumo_despesas, nao_categorizadas_limpo, resumo_receitas




def _processar_relatorio_seu_condominio_csv(arquivo_csv):
    """
    Lê o relatório CSV do sistema 'Seu Condomínio' (versão final).
    Esta versão está adaptada EXATAMENTE para a estrutura do arquivo CSV fornecido.
    """
    print("--- INICIANDO PROCESSAMENTO CSV (VERSÃO CORRETA) ---")
    try:
        arquivo_csv.seek(0)
        
        # Lê o CSV da forma padrão, que é a correta para este arquivo.
        df = pd.read_csv(
            arquivo_csv,
            encoding='latin-1',
            sep=',',
            decimal=',',
            thousands='.',
            quotechar='"'
        )
        print("DEBUG: CSV lido. Colunas originais:", df.columns.tolist())

        # Renomeia as colunas que realmente existem no CSV para o nosso padrão.
        df.rename(columns={
            'Data Pagamento': 'Data',
            'Total Pago': 'Valor',
        }, inplace=True)

        # Remove linhas que não são transações (sem data de pagamento)
        df.dropna(subset=['Data', 'Tipo'], inplace=True)

        # Cria uma descrição mais completa para facilitar a identificação
        df['Descricao'] = df['Grupo'].fillna('') + ' - ' + df['Subgrupo'].fillna('') + ' - ' + df['Descrição'].fillna('')
        
        # Adiciona a coluna 'Fornecedor' vazia, pois ela não existe neste CSV
        df['Fornecedor'] = ''

        # Seleciona e ordena as colunas para o DataFrame final padronizado
        df_final = df[['Data', 'Valor', 'Tipo', 'Descricao', 'Fornecedor']].copy()

        # Garante os tipos de dados corretos
        df_final['Data'] = pd.to_datetime(df_final['Data'], dayfirst=True, errors='coerce')
        df_final['Valor'] = pd.to_numeric(df_final['Valor'], errors='coerce').fillna(0)
        
        # Remove quaisquer linhas que possam ter falhado na conversão de data
        df_final.dropna(subset=['Data'], inplace=True)

        print(f"--- PROCESSAMENTO CSV CONCLUÍDO. {len(df_final)} transações encontradas. ---")
        return df_final

    except KeyError as e:
        raise ValueError(f"A coluna esperada {e} não foi encontrada no arquivo CSV. Verifique se o relatório exportado está correto.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ValueError(f"Não foi possível processar o arquivo CSV do Seu Condomínio. Erro: {e}")
    


def conciliar_dataframes(df_banco, df_relatorio):

    print("--- INICIANDO MOTOR DE CONCILIAÇÃO ---")
    
    # Padronizando colunas para a comparação.
    banco_comp = df_banco[['Data', 'Valor', 'Topico', 'Descricao']].copy()
    banco_comp.rename(columns={'Topico': 'Tipo'}, inplace=True)
        
    relatorio_comp = df_relatorio[['Data', 'Valor', 'Tipo', 'Descricao', 'Fornecedor']].copy()

    # Arredonda valores para 2 casas decimais para evitar problemas de ponto flutuante
    banco_comp['Valor'] = banco_comp['Valor'].round(2)
    relatorio_comp['Valor'] = relatorio_comp['Valor'].round(2)

    # Adiciona um identificador único para cada linha para lidar com transações duplicadas no mesmo dia/valor
    banco_comp['id_unico'] = banco_comp.groupby(['Data', 'Valor', 'Tipo']).cumcount()
    relatorio_comp['id_unico'] = relatorio_comp.groupby(['Data', 'Valor', 'Tipo']).cumcount()

        # Realiza o 'merge' dos dois DataFrames para encontrar as correspondências e diferenças
    conciliacao_df = pd.merge(
    banco_comp,
    relatorio_comp,
    on=['Data', 'Valor', 'Tipo', 'id_unico'],
    how='outer',
    suffixes=('_banco', '_relatorio'),
    indicator=True
    )

        # Separa os resultados com base no indicador '_merge'
    conciliadas = conciliacao_df[conciliacao_df['_merge'] == 'both']
    apenas_banco = conciliacao_df[conciliacao_df['_merge'] == 'left_only']
    apenas_relatorio = conciliacao_df[conciliacao_df['_merge'] == 'right_only']

    print("--- CONCILIAÇÃO FINALIZADA ---")
    return conciliadas, apenas_banco, apenas_relatorio



def debug_csv_view(request):
    if request.method == 'POST' and request.FILES.get('arquivo_csv'):
        arquivo_csv = request.FILES['arquivo_csv']
        
        diagnostico = ["--- ANÁLISE BRUTA DO ARQUIVO CSV ---"]
        
        try:
            arquivo_csv.seek(0)
            # Lê as primeiras 15 linhas do arquivo
            linhas = arquivo_csv.readlines(15)
            
            for i, linha_bytes in enumerate(linhas):
                # Tenta decodificar a linha e conta as vírgulas
                try:
                    linha_texto = linha_bytes.decode('latin-1').strip()
                    contagem_virgulas = linha_texto.count(',')
                    diagnostico.append(f"Linha {i+1} ({contagem_virgulas} vírgulas): {linha_texto}")
                except Exception as e:
                    diagnostico.append(f"Linha {i+1}: Erro ao decodificar - {e}")

            return HttpResponse("<pre>" + "\n".join(diagnostico) + "</pre>")

        except Exception as e:
            return HttpResponse(f"Ocorreu um erro geral ao tentar ler o arquivo: {e}")

    # Formulário de upload para a página de debug
    return HttpResponse("""
        <h1>Ferramenta de Diagnóstico de CSV</h1>
        <p>Envie o arquivo .csv do "Seu Condomínio" que está causando o erro.</p>
        <form method="post" enctype="multipart/form-data">
            <input type="file" name="arquivo_csv" required>
            <button type="submit">Analisar Arquivo</button>
        </form>
    """)