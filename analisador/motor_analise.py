import pandas as pd
import numpy as np
from .models import Regra, Transacao, Extrato

# --- Funções de processamento (Especialistas) ---
def _processar_formato_pix(df):
    print("Formato PIX detectado.")
    df_padronizado = df.rename(columns={
        'Valor (R$)': 'Valor',
        'Remetente/Destinatario': 'Descricao',
        'Tipo de Pix': 'Tipo',
        'Data': 'Data'
    })
    
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    df_padronizado['Topico'] = np.where(df_padronizado['Tipo'] == 'Enviado', 'Despesa', 'Receita')
    return df_padronizado

def _processar_formato_nubank(df):
    print("Formato Nubank/CSV detectado.")
    df_padronizado = df.rename(columns={'Descrição': 'Descricao'})
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'] < 0, 'Despesa', 'Receita')
    df_padronizado['Valor'] = df_padronizado['Valor'].abs()
    return df_padronizado

def _processar_formato_sicoob(df):
    print("Formato Sicoob detectado.")
    df_padronizado = df.rename(columns={
        'Histórico': 'Descricao',
        'Valor Lançamento': 'Valor',
        'Data Lançamento': 'Data'
    })
    df_padronizado['Valor'] = pd.to_numeric(df_padronizado['Valor'], errors='coerce').fillna(0)
    df_padronizado['Topico'] = np.where(df_padronizado['Valor'] < 0, 'Despesa', 'Receita')
    df_padronizado['Valor'] = df_padronizado['Valor'].abs()
    return df_padronizado


# --- FUNÇÃO PRINCIPAL (O "MAESTRO") ---
def processar_extrato(arquivo_extrato, usuario_logado, extrato_obj):
    
    try:
        # AVISANDO AO PANDAS QUE A VÍRGULA É O SEPARADOR DECIMAL
        df = pd.read_excel(arquivo_extrato, decimal=',')
        df_com_skip = pd.read_excel(arquivo_extrato, skiprows=1, decimal=',')
    except Exception as e:
        raise ValueError(f"Não foi possível ler o ficheiro Excel. Erro: {e}")

    if 'Tipo de Pix' in df.columns and 'Situacao' in df.columns:
        df_processado = _processar_formato_pix(df)
    elif 'Identificador' in df.columns and 'Descrição' in df.columns:
        df_processado = _processar_formato_nubank(df)
    elif 'Histórico' in df_com_skip.columns and 'Valor Lançamento' in df_com_skip.columns:
        df_processado = _processar_formato_sicoob(df_com_skip)
    else:
        raise ValueError("Formato de extrato não reconhecido.")

    regras_do_usuario = Regra.objects.filter(usuario=usuario_logado)
    regras_de_categorizacao = {
        regra.palavra_chave: regra.categoria for regra in regras_do_usuario
    }

    def categorizar_transacao(descricao):
        if not isinstance(descricao, str):
            return 'Não categorizado'
        for palavra_chave, categoria in regras_de_categorizacao.items():
            if palavra_chave.lower() in descricao.lower():
                return categoria
        return 'Não categorizado'

    # --- CORREÇÃO NA LÓGICA DE LIMPEZA ---
    def _limpar_descricao_inteligente(descricao):
        # Converte para string para segurança
        descricao_str = str(descricao)
        
        # Se a descrição for nula ou vazia, retorna a própria descrição original
        if pd.isna(descricao) or not descricao_str.strip():
            return descricao_str
        
        try:
            parts = descricao_str.split(' - ')
            if len(parts) > 1:
                # Retorna a primeira parte relevante após o ' - '
                return parts[1].strip()
        except:
            pass
        # Se a limpeza falhar ou não encontrar o separador, retorna a descrição original
        return descricao_str
    
    # Garante que a coluna 'Descricao' é do tipo string e preenche valores nulos
    df_processado['Descricao'] = df_processado['Descricao'].fillna('').astype(str)
    
    # Aplica a limpeza e a categorização
    df_processado['DescricaoLimpa'] = df_processado['Descricao'].apply(_limpar_descricao_inteligente)
    df_processado['Subtopico'] = df_processado['Descricao'].apply(categorizar_transacao)
    # --- FIM DA CORREÇÃO ---

    Transacao.objects.filter(extrato=extrato_obj).delete()
    for index, linha in df_processado.iterrows():
        Transacao.objects.create(
            extrato=extrato_obj,
            usuario=usuario_logado,
            data=linha.get('Data', ''),
            descricao=linha.get('Descricao', ''), # <-- CORREÇÃO: Guarda a descrição ORIGINAL
            valor=linha.get('Valor', 0.0),
            topico=linha.get('Topico', ''),
            subtopico=linha.get('Subtopico', '')
        )
    
    df_receitas = df_processado[df_processado['Topico'] == 'Receita']
    df_despesas = df_processado[df_processado['Topico'] == 'Despesa']

    total_despesas = df_despesas['Valor'].sum()
    total_receitas = df_receitas['Valor'].sum()
    saldo_liquido = total_receitas - total_despesas

    resumo_despesas = df_despesas.groupby('Subtopico')['Valor'].sum().sort_values(ascending=False)
    resumo_receitas = df_receitas.groupby('Subtopico')['Valor'].sum().sort_values(ascending=False)
    
    nao_categorizadas_bruto = df_processado[df_processado['Subtopico'] == 'Não categorizado']
    colunas_desejadas = ['Topico', 'Data', 'DescricaoLimpa', 'Valor']
    nao_categorizadas_limpo = nao_categorizadas_bruto[colunas_desejadas]

    return total_receitas, total_despesas, saldo_liquido, resumo_despesas, nao_categorizadas_limpo, resumo_receitas
