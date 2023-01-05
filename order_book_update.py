# Python
import json

# Externals
import requests
import pandas as pd
from websocket import WebSocketApp


# Variables Globales
info = {}
cols = ['price', 'quantity']

def init_info(ticker: str) -> None:
    """
    Initialize global variable 'info' for the asset or assets.

    Args:
        ticker (str): ticker symbol of the asset.
    """      
    global info
    
    info[ticker] = {
        'asks': None,
        'bids': None,        
        'event_id': 0,
        'lastUpdateId' : 0,        
        'u_anterior': 0
        }


def validate_snapshot(msg: dict) -> bool:
    """Validates that snapshot gets the lastUpdateId key and the len for
       bids and asks are 1,000.

    Args:
        msg (dict): Request form Binance API formatted as a Dictionary

    Returns:
        bool: True if is a correct snapshot False if isn´'t
    """    
    if msg.get('lastUpdateId', False) and msg.get('asks', False) and msg.get('bids', False):
        if len(msg['asks']) == 1_000 and len(msg['bids']) == 1_000:
            return True
    
    return False


def create_dataframe(data:dict) -> pd.DataFrame:
    """Creates a Dataframe and stablish the price column as an index

    Args:
        data (dict): Data to convert passed as a Dictionary

    Returns:
        pd.DataFrame: Dataframe sorted in descending mode and setted the price column as the index
    """    
    df = pd.DataFrame(data, columns=cols)
    df.set_index('price', inplace=True)
    df.sort_index(ascending=False, inplace=True)
    df.index = df.index.astype('float64')
    df['quantity'] = df['quantity'].astype("float64")
    return df


def get_snapshot(ticker: str) -> None:
    """Gets the Order Book from Binance for the Coin and stores it in the 
       global variable 'info'

    Args:
        ticker (str): Asset that we will seek the Order Bok for

    Raises:
        ValueError: If the Order Book is'n retrieved correctly
    """    
    global info
    url = "https://fapi.binance.com/fapi/v1/depth"
    params = {"symbol": ticker.upper(), "limit": 1000}
    response = requests.get(url, params=params)
    response = response.json()
    
    if not validate_snapshot(response):
        raise ValueError("No se pudo Obtener el Snapshot Correctamente")

    info[ticker]['lastUpdateId'] =  response['lastUpdateId']
    info[ticker]['asks'] = create_dataframe(response['asks'])
    info[ticker]['bids'] = create_dataframe(response['bids'])


def create_event(data:dict) -> dict:
    """Creates and stores the data received from the event

    Args:
        data (dict): Data from the Webspcket message as a Dictionary

    Returns:
        dict: A dictionary with the data from the event
    """    
    
    data = data.get("data", {})
    u = data.get('u',0)
    U = data.get('U',0)
    pu = data.get('pu',0)
    asks = create_dataframe(data.get('a',[]))
    bids = create_dataframe(data.get('b',[]))
    
    return {
        'u': u,
        'U': U,
        'pu': pu,
        'asks': asks,
        'bids': bids
    }


def on_close(ws):
    """Cloeses the Websocket

    Args:
        ws (_type_): _Websocket Objetc
    """    
    ws.close()


# esta funcion sera la encargada de actualizar el order book del snapshot obtenido
def process_event(ticker: str, new_asks:dict, new_bids:dict):
    """_summary_

    Args:
        ticker (str): _description_
        new_asks (dict): _description_
        new_bids (dict): _description_
    """    
    # datos del snapshot
    asks_df = info[ticker]['asks']
    bids_df = info[ticker]['bids']

    #print(asks_df)
    # datos a actualizar
    new_asks_df = new_asks
    new_bids_df = new_bids

    
    print(f"{'+'*50}")
    print("ACTUALIZANDO ORDER BOOK")
    print(f"{'+'*50}")

    # Actualizamos los datos que están en ambos DataFrames, con esto se modifica asks_df y bids_df
    asks_df.update(new_asks_df)
    #print(asks_df)
    bids_df.update(new_bids_df)
    #print(bids_df)
    # Ahora pasamos los datos que no están en asks_df ni en bids_df pero si en los nuevos
    # Empezamos con asks para ver el proceso paso a paso

    # Combinamos los datos, tomando asks_df como los datos que permaneces y agregando los de new_asks_df
    asks_df = asks_df.combine_first(new_asks_df)
    
    # Obtenemos el DataFrame con la condición para obtener todos los precios con cantidad cero
    condition =  asks_df[asks_df['quantity'] == 0]    

    # Usamos el método drop, usando la condición y, a esta, obtenemos el indice para poder eliminar
    asks_df = asks_df.drop(condition.index)
    
    # Hacemos lo mismo para los bids
    bids_df = bids_df.combine_first(new_bids_df)
    condition =  bids_df[bids_df['quantity'] == 0]
    bids_df = bids_df.drop(condition.index)

    info[ticker]['asks'] = asks_df
    info[ticker]['bids'] = bids_df

    # Hasta aqui tenemos la actualización constante del Order Book


def on_message(ws, msg, ticker):
    """Process de message and manage the sequence for the Order Book to Update

    Args:
        ws (_type_): Websocket Object
        msg (_type_): Message from the socket
        ticker (_type_): asset to know wich Coin Order Book is needed
    """    
    global info

    # aqui llega el mensaje como string
    # lo pasamos a diccionairo
    # Hata aqui tenemos el diccionario de la info
    data = json.loads(msg) 
    
    # Obtenemos datos del evento
    pu_actual = data['data']['pu']
    u_actual = data['data']['u']
    U = data['data']['U']
    
    new_asks = create_dataframe(data['data']['a'])
    new_bids = create_dataframe(data['data']['b'])
    u_anterior = info[ticker]['u_anterior']
    asks = info[ticker]['asks']
    bids = info[ticker]['bids']

    if pu_actual != u_anterior:
        get_snapshot(ticker)        
        info[ticker]['event_id'] = 0        
        print("Se obtuvo Snapshot ya que pu != u_anterior")
        info[ticker]['u_anterior'] = u_actual
    
    else:
        # Para procesar el evento tiene que ser u>= lastUpdateId
        lastUpdateId = info[ticker]['lastUpdateId']
        #print("Verificando si el evento es procesable")
        if u_actual >= lastUpdateId:            
            # El primer dato a procesar debe tener U <= lastUpdateId AND u >= lastUpdateId
            # Solo aumentaremos el número del evento por primera vez aqui
            if info[ticker]['event_id'] == 0 and U<=lastUpdateId and u_actual>= lastUpdateId:
                info[ticker]['u_anterior'] = u_actual
                info[ticker]['event_id'] += 1
                process_event(ticker, new_asks, new_bids)
                

            # Este if solo entrará cuando el evento sea mayor a 0, es decir, hasta el segundo evento
            elif info[ticker]['event_id'] > 0:                
                info[ticker]['u_anterior'] = u_actual
                info[ticker]['event_id'] += 1
                process_event(ticker, new_asks, new_bids)
        else:
            info[ticker]['u_anterior'] = u_actual
    
    # Hacemos que el evento anterior sea ahora el que fue nuestro evento actual


def start_ws(ticker:str):
    ws_url = f"wss://fstream.binance.com/stream?streams={ticker.lower()}@depth"
    # Aquí necesitamos enviar la dirección de memoria de on_message pera necesitamos enviar el
    # ticker como argumento. Esto lo logramos con una función anómina (lambda) 
    ws = WebSocketApp(url=ws_url, on_message=lambda ws, msg: on_message(ws, msg, ticker), on_close=on_close)
    ws.run_forever() 


def main():
    global info
    
    ticker = "btcusdt"
    # 1. Iniciamos la variable que guarda la información
    init_info(ticker)
        
    # 2. Iniciamos Websocket
    start_ws(ticker)


if __name__ == '__main__':
    main()