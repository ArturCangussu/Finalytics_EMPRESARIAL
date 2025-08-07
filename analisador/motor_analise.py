# motor_analise.py (VERSÃO FINAL COM SUPER-FUNÇÃO DE DATA)

import pandas as pd
import numpy as np
from .models import Regra, Transacao, Extrato

def converter_data_robusta(data):
    """
    Converte qualquer formato de data vindo do Excel de forma robusta.
    - Lida com datas que já são do tipo datetime.
    - Lida com datas em formato de texto (dd/mm/aaaa).
    - Lida com datas numéricas (formato serial do Excel).
    """
    # Se já for um tipo de data do pandas/numpy, retorna sem fazer nada.
    if isinstance(data, (pd.Timestamp, np.datetime64)):
        return data
    try:
        # Tenta converter como número (data serial do Excel).
        # A origem '1899-12-30' é o padrão para Excel no Windows.
        return pd.to_datetime(data, unit='D', origin='1899-12-30')
    except (ValueError, TypeError):
        # Se não for número, tenta como texto no formato brasileiro.
        return pd.to_datetime(data, dayfirst=True, errors='coerce')

def _processar_formato_caixa(df):
    print("Formato Caixa Federal detectado.")
    df['origem_descricao'] = np.where(df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True).isna(), 'Historico', 'Nome/Razao Social')
    df['Nome/Razão Social'] = df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True)
    df['Nome/Razão Social'] = df['Nome/Razão Social'].fillna(df['Histórico'])
    df_padronizado = df.rename(columns={'Valor Lançamento': 'Valor', 'Nome/Razão Social': 'Descricao', 'Data Lançamento': 'Data'})
    
    # APLICA A SUPER-FUNÇÃO DE CONVERSÃO DE DATA
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)
    
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'] < 0, 'Despesa', 'Receita')
    df_padronizado['Valor'] = df_padronizado['Valor'].abs()
    return df_padronizado

def _processar_formato_sicoob(df):
    print("Formato Sicoob detectado.")
    df['origem_descricao'] = 'Nome/Razao Social'
    df_padronizado = df.rename(columns={'Nome/Razão Social': 'Descricao', 'VALOR': 'Valor', 'DATA': 'Data'})
    
    # APLICA A SUPER-FUNÇÃO DE CONVERSÃO DE DATA
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)

    df_padronizado['Valor'] = df_padronizado['Valor'].astype(str)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'].str.contains('C', na=False), 'Receita', 'Despesa')
    df_padronizado['Valor'] = df_padronizado['Valor'].str.replace('C', '', regex=False).str.replace('D', '', regex=False).str.strip()
    df_padronizado['Valor'] = df_padronizado['Valor'].str.replace('.', '', regex=False)
    df_padronizado['Valor'] = df_padronizado['Valor'].str.replace(',', '.', regex=False)
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    return df_padronizado

def processar_extrato(arquivo_extrato, usuario_logado, extrato_obj):
    try:
        df_normal = pd.read_excel(arquivo_extrato)
        df_com_skip = pd.read_excel(arquivo_extrato, skiprows=1)
    except Exception as e:
        raise ValueError(f"Não foi possível ler o ficheiro Excel. Erro: {e}")

    if 'Data Lançamento' in df_com_skip.columns and 'Valor Lançamento' in df_com_skip.columns:
        df_processado = _processar_formato_caixa(df_com_skip)
    elif 'Nome/Razão Social' in df_normal.columns and 'VALOR' in df_normal.columns:
        df_processado = _processar_formato_sicoob(df_normal)
    else:
        print("Colunas encontradas (tentativa 1):", df_normal.columns)
        print("Colunas encontradas (tentativa 2):", df_com_skip.columns)
        raise ValueError("Formato de extrato não reconhecido.")

    df_processado.dropna(subset=['Data'], inplace=True)
    
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
    
    df_receitas = df_processado[df_processado['Topico'] == 'Receita']
    df_despesas = df_processado[df_processado['Topico'] == 'Despesa']
    total_despesas = df_despesas['Valor'].sum()
    total_receitas = df_receitas['Valor'].sum()
    saldo_liquido = total_receitas - total_despesas
    resumo_despesas = df_despesas.groupby('Subtopico')['Valor'].sum().sort_values(ascending=False)
    resumo_receitas = df_receitas.groupby('Subtopico')['Valor'].sum().sort_values(ascending=False)
    nao_categorizadas_bruto = df_processado[df_processado['Subtopico'] == 'Não categorizado']
    colunas_desejadas = ['Topico', 'Data', 'Descricao', 'Valor', 'origem_descricao']
    nao_categorizadas_limpo = nao_categorizadas_bruto.reindex(columns=colunas_desejadas)

    return total_receitas, total_despesas, saldo_liquido, resumo_despesas, nao_categorizadas_limpo, resumo_receitas