import os
import json
import requests
from datetime import datetime, timedelta

# Série 4390: Taxa de juros - Selic acumulada no mês (% a.m.)
BCB_SELIC_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados"
DATA_INICIAL_PADRAO = "01/01/1995"

# Salva o cache em AppData\Local\pactuacalc — gravavel mesmo dentro de um .exe empacotado
_APP_DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "pactuacalc",
)
os.makedirs(_APP_DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(_APP_DATA_DIR, "selic_history.json")

def load_selic_history():
    """Carrega o histórico local de taxas Selic. Retorna lista vazia se não existir."""
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao carregar o arquivo {FILE_PATH}: {e}")
    return []

def _get_last_date(history):
    """Retorna a última data salva no histórico ou a data padrão de início."""
    if not history:
        return DATA_INICIAL_PADRAO
    last_record = history[-1]
    return last_record.get('data', DATA_INICIAL_PADRAO)

def update_selic_history():
    """
    Verifica a última data local e busca as taxas faltantes no BCB até o dia de hoje.
    Salva e retorna o histórico atualizado.
    """
    history = load_selic_history()
    last_date_str = _get_last_date(history)
    
    # Prepara as datas
    hoje = datetime.now()
    hoje_str = hoje.strftime("%d/%m/%Y")
    
    # Se já tivermos dados, pegamos a partir do próximo dia da última data salva.
    # Como a Selic é mensal, o BCB costuma indexar pela data do primeiro dia do mês.
    # Mas passar a mesma data da última requisição pode trazer o último mês de novo.
    # O BCB lida bem com sobreposições, a gente pode filtrar se vier duplicado.
    if history:
        try:
            last_date_obj = datetime.strptime(last_date_str, "%d/%m/%Y")
            # Adicionamos 1 dia para não buscar a mesma data
            start_date_obj = last_date_obj + timedelta(days=1)
            data_inicial_busca = start_date_obj.strftime("%d/%m/%Y")
        except ValueError:
            data_inicial_busca = last_date_str
    else:
        data_inicial_busca = DATA_INICIAL_PADRAO

    # Se a data inicial da busca já passou de hoje, não precisa buscar
    try:
        if datetime.strptime(data_inicial_busca, "%d/%m/%Y") > hoje:
            return history
    except ValueError:
        pass

    params = {
        "formato": "json",
        "dataInicial": data_inicial_busca,
        "dataFinal": hoje_str
    }
    
    try:
        response = requests.get(BCB_SELIC_URL, params=params, timeout=10)
        response.raise_for_status()
        new_data = response.json()
        
        if new_data:
            # Filtra registros que porventura já existam (baseado na data)
            existing_dates = {item['data'] for item in history}
            for item in new_data:
                if item['data'] not in existing_dates:
                    history.append(item)
                    existing_dates.add(item['data'])
                    
            # Salva o arquivo atualizado
            with open(FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
                
    except requests.RequestException as e:
        print(f"Erro ao buscar taxas Selic no Banco Central: {e}")
        # Retorna o histórico existente mesmo se a atualização falhar
        
    return history

def get_selic_rate(data_str):
    """
    Função utilitária para pegar a taxa de um mês específico.
    A data_str deve estar no formato 'dd/mm/yyyy'.
    Como a taxa é mensal, geralmente é o dia '01'.
    """
    history = load_selic_history()
    for item in history:
        if item.get('data') == data_str:
            return float(item.get('valor', 0.0))
    return None

def get_mean_selic_12_months(data_base_str: str) -> float:
    """
    Retorna a média aritmética das 12 taxas Selic mensais imediatamente 
    anteriores ao mês/ano da data_base_str fornecida.
    """
    history = load_selic_history()
    if not history:
        return 0.0

    # Parse da data_base
    from pactuacalc.models import parse_iso_date
    data_base = parse_iso_date(data_base_str)
    if not data_base:
        return 0.0

    # Queremos itens cuja data (01/MM/YYYY) seja estritamente anterior a Mês/Ano da data_base.
    # Ex: data_base = 15/05/2026. Queremos tudo antes de 01/05/2026.
    base_month_start = datetime(data_base.year, data_base.month, 1).date()

    valid_rates = []
    for item in history:
        item_date = parse_iso_date(item['data'])
        if item_date and item_date < base_month_start:
            valid_rates.append(float(item.get('valor', 0.0)))
            
    if not valid_rates:
        return 0.0
        
    last_12 = valid_rates[-12:]
    return sum(last_12) / len(last_12)

def get_last_12_selic_rates(data_base_str: str) -> list[dict]:
    """
    Retorna a lista com os últimos 12 registros da Selic anteriores à data_base_str.
    """
    history = load_selic_history()
    if not history:
        return []

    from pactuacalc.models import parse_iso_date
    data_base = parse_iso_date(data_base_str)
    if not data_base:
        return []

    from datetime import datetime
    base_month_start = datetime(data_base.year, data_base.month, 1).date()

    valid_rates = []
    for item in history:
        item_date = parse_iso_date(item['data'])
        if item_date and item_date < base_month_start:
            valid_rates.append(item)
            
    return valid_rates[-12:]

