# motor_analise.py (VERSÃO FINAL COM DETECÇÃO CORRETA PARA SICOOB)

import pandas as pd
import numpy as np
from .models import Regra, Transacao, Extrato

def converter_data_robusta(data):
    if isinstance(data, (pd.Timestamp, np.datetime64)):
        return data
    try:
        return pd.to_datetime(data, unit='D', origin='1899-12-30')
    except (ValueError, TypeError):
        return pd.to_datetime(data, dayfirst=True, errors='coerce')

def _processar_formato_caixa(df):
    print("Formato Caixa Federal detectado.")
    # ... (Esta função já está correta, não precisa de mudanças)
    df['origem_descricao'] = np.where(df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True).isna(), 'Historico', 'Nome/Razao Social')
    df['Nome/Razão Social'] = df['Nome/Razão Social'].replace(r'^\s*$', np.nan, regex=True)
    df['Nome/Razão Social'] = df['Nome/Razão Social'].fillna(df['Histórico'])
    df_padronizado = df.rename(columns={'Valor Lançamento': 'Valor', 'Nome/Razão Social': 'Descricao', 'Data Lançamento': 'Data'})
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'] < 0, 'Despesa', 'Receita')
    df_padronizado['Valor'] = df_padronizado['Valor'].abs()
    return df_padronizado

# --- ESPECIALISTA 2: Processa o formato "Sicoob" ---
def _processar_formato_sicoob(df):
    print("Formato Sicoob detectado.")

    df['origem_descricao'] = 'Historico'
    df_padronizado = df.rename(columns={
        'HISTÓRICO': 'Descricao',
        'VALOR': 'Valor',
        'DATA': 'Data'
    })
    
    df_padronizado['Data'] = df_padronizado['Data'].apply(converter_data_robusta)

    # ================================================================
    # =========== BLOCO DE PROCESSAMENTO DE VALOR CORRIGIDO ==========
    # ================================================================
    df_padronizado['Valor'] = df_padronizado['Valor'].astype(str)
    
    # A lógica para definir o Tópico pode ser mais simples: se tiver sinal de menos ou a letra 'D', é despesa.
    df_padronizado['Topico'] = np.where(
        df_padronizado['Valor'].str.contains('C', na=False), 
        'Receita', 
        'Despesa'
    )

    # Limpeza mais robusta do valor, removendo tudo que não é número, vírgula ou sinal de menos
    df_padronizado['Valor'] = (
        df_padronizado['Valor']
        .str.replace('C', '', regex=False)
        .str.replace('D', '', regex=False)
        .str.replace('.', '', regex=False)      # Remove o separador de milhar
        .str.replace(',', '.', regex=False)      # Troca a vírgula decimal por ponto
        .str.replace(r'\s+', '', regex=True)     # Remove TODOS os espaços em branco
    )
    
    # Converte para número. Agora strings como '-50.00' serão convertidas corretamente.
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    
    # Passo final e crucial: pega o valor absoluto (positivo), pois o Tópico já define se é despesa.
    df_padronizado['Valor'] = df_padronizado['Valor'].abs()
    # ================================================================
    
    return df_padronizado

def processar_extrato(arquivo_extrato, usuario_logado, extrato_obj):
    try:
        df_normal = pd.read_excel(arquivo_extrato)
        df_com_skip = pd.read_excel(arquivo_extrato, skiprows=1)
    except Exception as e:
        raise ValueError(f"Não foi possível ler o ficheiro Excel. Erro: {e}")

    # Condição para CAIXA
    if 'Data Lançamento' in df_com_skip.columns and 'Valor Lançamento' in df_com_skip.columns:
        df_processado = _processar_formato_caixa(df_com_skip)
    # ================================================================
    # =========== CONDIÇÃO CORRIGIDA PARA O SICOOB AQUI ==============
    # ================================================================
    # Agora ele procura por 'DATA' e 'HISTÓRICO' no df_com_skip, que é o correto
    elif 'DATA' in df_com_skip.columns and 'HISTÓRICO' in df_com_skip.columns:
        # E também passa o df_com_skip para o processador
        df_processado = _processar_formato_sicoob(df_com_skip)
    # ================================================================
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