# motor_analise.py (VERSÃO COM LIMPEZA INTELIGENTE DA DESCRIÇÃO)

import pandas as pd
import numpy as np
from .models import Regra, Transacao, Extrato
from bs4 import BeautifulSoup
import zipfile
import re
import io
import csv


def sanitize_excel_file(uploaded_file):
    print("--- INICIANDO SANITIZAÇÃO DO ARQUIVO EXCEL ---")
    uploaded_file.seek(0)
    sanitized_file_in_memory = io.BytesIO()
    with zipfile.ZipFile(sanitized_file_in_memory, 'w', zipfile.ZIP_DEFLATED) as z_out:
        with zipfile.ZipFile(uploaded_file, 'r') as z_in:
            for item in z_in.infolist():
                content = z_in.read(item.filename)
                if item.filename.startswith('xl/worksheets/sheet'):
                    xml_content_str = content.decode('utf-8')
                    sanitized_xml_content = re.sub(r' r="\d+"', '', xml_content_str)
                    if xml_content_str != sanitized_xml_content:
                        print("DEBUG: Sanitização aplicada.")
                    z_out.writestr(item, sanitized_xml_content.encode('utf-8'))
                else:
                    z_out.writestr(item, content)
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
        conteudo = arquivo_html.read().decode('utf-8', errors='ignore')
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
            
            celulas_obj = linha_tr.find_all('td')
            
            
            if len(celulas_obj) == 4 and celulas_obj[0].get_text().strip() and "SALDO" not in celulas_obj[2].get_text().upper():
                
                data = celulas_obj[0].get_text().strip()
                documento = celulas_obj[1].get_text().strip()
                
                # ==============================================================================
                # === LÓGICA PARA EXTRAIR APENAS A ÚLTIMA LINHA DA DESCRIÇÃO ===
                # ==============================================================================
                descricao_cell = celulas_obj[2]
                # Pega todo o texto, usando '\n' como separador para manter as linhas
                texto_completo_com_linhas = descricao_cell.get_text(separator='\n').strip()
                # Divide o texto em uma lista de linhas e remove as que estiverem vazias
                linhas = [linha.strip() for linha in texto_completo_com_linhas.split('\n') if linha.strip()]
                
                descricao_final = ' '.join(linhas) # Um fallback caso a lógica falhe
                if linhas:
                
                    descricao_final = linhas[-1]
                # ==============================================================================

                valor_str = celulas_obj[3].get_text().strip()

                # Lógica para extrair C/D do valor 
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



def _processar_formato_caixa(df):
    print("Formato Caixa Federal detectado.")
    
    # --- INÍCIO DA CORREÇÃO ---
    # 1. Filtra o DataFrame para manter apenas linhas que são transações reais.
    # Primeiro, garantimos que as colunas de data e valor existam.
    if 'Data Lançamento' not in df.columns or 'Valor Lançamento' not in df.columns:
        raise ValueError("Colunas 'Data Lançamento' ou 'Valor Lançamento' não encontradas no extrato da Caixa.")

    # Converte a coluna de data, tratando erros. Linhas sem data válida (como cabeçalhos) se tornarão NaT (Not a Time).
    df['Data Lançamento'] = pd.to_datetime(df['Data Lançamento'], dayfirst=True, errors='coerce')

    # Remove todas as linhas onde a data não pôde ser convertida (linhas de cabeçalho, saldo, etc.)
    df.dropna(subset=['Data Lançamento'], inplace=True)
    
    # Remove linhas onde o valor do lançamento é zero ou nulo, que não são transações relevantes.
    df['Valor Lançamento'] = pd.to_numeric(df['Valor Lançamento'], errors='coerce')
    df.dropna(subset=['Valor Lançamento'], inplace=True)
    df = df[df['Valor Lançamento'] != 0]
    # --- FIM DA CORREÇÃO ---

    # O restante do seu código original continua a partir daqui, agora com dados limpos.
    df['origem_descricao'] = np.where(df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True).isna(), 'Historico', 'Nome/Razao Social')
    df['Nome/Razão Social'] = df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True)
    df['Nome/Razão Social'] = df['Nome/Razão Social'].fillna(df['Histórico'])
    
    # Renomeia as colunas DEPOIS de usá-las para o filtro
    df_padronizado = df.rename(columns={'Valor Lançamento': 'Valor', 'Nome/Razão Social': 'Descricao', 'Data Lançamento': 'Data'})
    
    # A lógica de tipo e valor absoluto agora opera em um DataFrame limpo
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
    return df_padronizado[['Data', 'Descricao', 'Valor', 'Topico']]


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




# --- FUNÇÃO PARA LER O RELATÓRIO "SEU CONDOMÍNIO" (TRATANDO COMO EXCEL) ---
def _processar_relatorio_seu_condominio_csv(arquivo_csv):
    """
    Lê o relatório CSV do "Seu Condomínio", implementando corretamente a lógica de
    "máquina de estados" para classificar Receitas e Despesas.
    """
    print("--- INICIANDO PROCESSAMENTO CSV (LÓGICA DE ESTADO CORRIGIDA) ---")
    try:
        arquivo_csv.seek(0)
        arquivo_csv_texto = io.TextIOWrapper(arquivo_csv, encoding='utf-8')
        reader = csv.reader(arquivo_csv_texto, delimiter=',', quotechar='"')

        dados_limpos = []
        current_tipo = '' # Inicia sem tipo definido

        for i, row in enumerate(reader):
            # Ignora linhas vazias ou o cabeçalho original
            if not row or not row[0] or 'pagador_fornecedor' in row[0]:
                continue

            primeira_coluna = row[0].upper()

            # 1. MUDANÇA DE ESTADO: Procura por RECEITAS ou DESPESAS
            if 'RECEITAS' in primeira_coluna:
                current_tipo = 'Receita'
                continue 
            
            elif 'DESPESAS' in primeira_coluna:
                current_tipo = 'Despesa'
                continue

            # 2. PROCESSAMENTO DE TRANSAÇÃO
            # Uma transação válida tem 5 campos e uma data na 4ª posição (índice 3)
            if len(row) >= 5 and '/' in row[3]:
                descricao_item, _, fornecedor, data, valor_str = row[:5]
                
                # Ignora a linha de cabeçalho que pode ser confundida com uma transação
                if "CONTABILIZADO" in data.upper():
                    continue

                valor_limpo = pd.to_numeric(valor_str, errors='coerce')

                # Adiciona a transação à lista com o TIPO do estado atual
                if current_tipo: # Só adiciona se já estivermos dentro de uma seção
                    dados_limpos.append({
                        'Tipo': current_tipo,
                        'Data': data,
                        'Descricao': descricao_item,
                        'Fornecedor': fornecedor,
                        'Valor': valor_limpo
                    })

        if not dados_limpos:
            raise ValueError("Nenhuma linha de transação válida foi encontrada no arquivo CSV.")

        df_final = pd.DataFrame(dados_limpos)
        df_final['Data'] = pd.to_datetime(df_final['Data'], dayfirst=True, errors='coerce')
        df_final.dropna(subset=['Data'], inplace=True)
        df_final.fillna({'Valor': 0, 'Fornecedor': '', 'Descricao': ''}, inplace=True)
        
        print(f"--- PROCESSAMENTO CSV CONCLUÍDO. {len(df_final)} transações encontradas. ---")
        return df_final
        
    except Exception as e:
        raise ValueError(f"Não foi possível processar o arquivo CSV do Seu Condomínio. Erro: {e}")
    


def conciliar_dataframes(df_banco, df_relatorio):
    """Compara os dois DataFrames e retorna as diferenças."""
    print("--- INICIANDO MOTOR DE CONCILIAÇÃO ---")
    banco_comp = df_banco.copy()
    banco_comp.rename(columns={'Topico': 'Tipo'}, inplace=True)
    if 'Descricao' in banco_comp.columns:
        cnpj_seu_condominio = '14.488.585 0001-45'
        # Encontra as linhas onde a descrição do banco contém o CNPJ
        filtro_cnpj = banco_comp['Descricao'].str.contains(cnpj_seu_condominio, na=False)
        # Nessas linhas, substitui a descrição inteira por 'Seu Condomínio'
        banco_comp.loc[filtro_cnpj, 'Descricao'] = 'Seu Condomínio'
    relatorio_comp = df_relatorio.copy()

    banco_comp['Data'] = pd.to_datetime(banco_comp['Data']).dt.normalize()
    relatorio_comp['Data'] = pd.to_datetime(relatorio_comp['Data']).dt.normalize()
    banco_comp['Valor'] = banco_comp['Valor'].round(2)
    relatorio_comp['Valor'] = relatorio_comp['Valor'].round(2)
    banco_comp['id_unico'] = banco_comp.groupby(['Data', 'Valor', 'Tipo']).cumcount()
    relatorio_comp['id_unico'] = relatorio_comp.groupby(['Data', 'Valor', 'Tipo']).cumcount()
    conciliacao_df = pd.merge(banco_comp, relatorio_comp, on=['Data', 'Valor', 'Tipo', 'id_unico'], how='outer', suffixes=('_banco', '_relatorio'), indicator=True)
    conciliadas = conciliacao_df[conciliacao_df['_merge'] == 'both']
    apenas_banco = conciliacao_df[conciliacao_df['_merge'] == 'left_only']
    apenas_relatorio = conciliacao_df[conciliacao_df['_merge'] == 'right_only']
    print("--- CONCILIAÇÃO FINALIZADA ---")
    return conciliadas, apenas_banco, apenas_relatorio