from django.db import models
from django.contrib.auth.models import User


class Extrato(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    mes_referencia = models.CharField(max_length=50, help_text="Ex: Julho/2025")
    data_upload = models.DateTimeField(auto_now_add=True) # Salva a data do upload automaticamente

    def __str__(self):
        return f"{self.mes_referencia} (Upload por: {self.usuario.username})"


class Regra(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    palavra_chave = models.CharField(max_length=100)
    categoria = models.CharField(max_length=100)

    def __str__(self):
        return f"'{self.palavra_chave}' -> '{self.categoria}' (Usuário: {self.usuario.username})"


class Transacao(models.Model):
    # Link para o extrato ao qual esta transação pertence
    extrato = models.ForeignKey(Extrato, on_delete=models.CASCADE, null=True) # ADICIONADO

    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    data = models.CharField(max_length=20)
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    topico = models.CharField(max_length=50)
    subtopico = models.CharField(max_length=100)
    origem_descricao = models.CharField(max_length=50, null=True, blank=True)
    categorizacao_manual = models.BooleanField(default=False)



    def __str__(self):
        return f"{self.data} - {self.descricao} - {self.valor}"
    

    @property
    def descricao_limpa(self):
        """
        Retorna uma versão limpa da descrição, tentando extrair a parte mais
        relevante, assim como na view do relatório.
        """
        descricao_str = str(self.descricao or '') # Garante que temos uma string
        if not descricao_str.strip():
            return descricao_str 

        try:
            parts = descricao_str.split(' - ')
            if len(parts) > 1:
                
                for part in parts[1:]:
                    cleaned_part = part.strip()
                    
                    if cleaned_part and not any(char.isdigit() for char in cleaned_part[:4]):
                        return cleaned_part
                
                
                return parts[1].strip()
        except Exception:
            
            return descricao_str
            
        
        return descricao_str