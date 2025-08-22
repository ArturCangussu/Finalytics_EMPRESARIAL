# Finanalytics - Conciliador Financeiro


Aplicação web Django que automatiza a conciliação de extratos bancários contra relatórios externos.

---

### 📸 Screenshots

<p align="center">
  <img src="https://github.com/user-attachments/assets/81698ce0-d2e7-4aca-a819-311b930d455c" width="32%" alt="Tela de Upload de Arquivos">
  <img src="https://github.com/user-attachments/assets/b290dc69-eb4a-4c78-8f34-70745f280ffb" width="32%" alt="Relatório de Conciliação">
  <img src="https://github.com/user-attachments/assets/91bb7e6c-d7ec-443f-bb25-6a9b4d213b09" width="32%" alt="Relátório de Conciliação">
</p>
---

### 🎯 Sobre o Projeto

O processo de conciliação financeira em muitas empresas, como administradoras de condomínio, é uma tarefa crítica, porém extremamente manual e demorada. Profissionais precisam comparar visualmente extratos bancários (em formatos variados como .xlsx e .html) com relatórios gerados por sistemas internos (.csv), linha por linha. Este método é ineficiente, suscetível a erros humanos e consome horas de trabalho que poderiam ser usadas em análises mais estratégicas.

Por que ele foi criado?
O Finanalytics Empresarial foi criado para eliminar completamente essa ineficiência. A ideia nasceu da necessidade de uma ferramenta que pudesse centralizar e automatizar a validação de registros financeiros, trazendo velocidade e, acima de tudo, confiança para o processo de fechamento mensal.

Qual o objetivo?
O objetivo principal do projeto é fornecer uma aplicação web robusta e intuitiva onde o usuário possa simplesmente fazer o upload do extrato bancário e de um ou mais relatórios do sistema interno. A plataforma então assume a responsabilidade de:

Processar e padronizar os dados de fontes e formatos diferentes, utilizando Pandas para a manipulação e BeautifulSoup para o parsing de HTML.

Executar a conciliação automática, cruzando as informações com base em data e valor.

Apresentar um relatório claro e imediato, destacando:

✅ Transações Conciliadas: Lançamentos que batem perfeitamente.

🚨 Divergências no Banco: Lançamentos que existem apenas no extrato bancário (possíveis omissões no sistema interno).

⚠️ Divergências no Relatório: Lançamentos que existem apenas no relatório (possíveis erros ou recebimentos não efetivados).

Em resumo, o Finanalytics transforma um processo manual, lento e arriscado em uma tarefa automatizada, rápida e confiável.

---

### ✨ Funcionalidades Principais

-   ✅ Upload de múltiplos formatos de arquivo (.xlsx, .html, .csv).
-   ✅ Conciliação automática de transações.
-   ✅ Identificação de divergências entre extrato e relatórios.
-   ✅ Interface web para gerenciamento e visualização de dados.

---

### 🛠️ Tecnologias Utilizadas

-   **Backend:** Python, Django
-   **Análise de Dados:** Pandas
-   **Frontend:** HTML, CSS, JavaScript, Bootstrap
-   **Banco de Dados:** SQLite

---

### 🚀 Como Executar o Projeto

(Esta parte mostra profissionalismo!)

```bash
# Clone o repositório
$ git clone [https://github.com/ArturCangussu/Finalytics_EMPRESARIAL/.git]

# Navegue até a pasta do projeto
$ cd Finalytics_EMPRESARIAL

# Instale as dependências
$ pip install -r requirements.txt

# Execute as migrações do banco de dados
$ python manage.py migrate

# Inicie o servidor
$ python manage.py runserver
```

---

### 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
