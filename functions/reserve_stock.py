import json
import boto3
from datetime import datetime, timezone

from aws_xray_sdk.core import patch_all
patch_all()

cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

ESTOQUE = {
    "espada": 10,
    "escudo": 5,
    "pocao": 50,
    "arco": 3
}

def log(severity, message, **kwargs):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": "reserve-stock",
        "message": message,
        **kwargs
    }))

def publicar_metrica(nome, valor):
    cloudwatch.put_metric_data(
        Namespace="OrderPipeline",
        MetricData=[{"MetricName": nome, "Value": valor, "Unit": "Count"}]
    )

def handler(event, context):
    order_id = event.get("order_id")
    produto = event.get("produto")
    quantidade = int(event.get("quantidade", 1))

    log("INFO", "Iniciando reserva", order_id=order_id,
        produto=produto, quantidade=quantidade)

    if produto not in ESTOQUE:
        log("ERROR", "Produto não encontrado", order_id=order_id, produto=produto)
        publicar_metrica("PedidosNaDLQ", 1)
        raise Exception(f"Produto '{produto}' não encontrado no estoque")

    if ESTOQUE[produto] < quantidade:
        log("ERROR", "Estoque insuficiente", order_id=order_id,
            disponivel=ESTOQUE[produto], solicitado=quantidade)
        publicar_metrica("PedidosNaDLQ", 1)
        raise Exception(f"Estoque insuficiente: disponível={ESTOQUE[produto]}, solicitado={quantidade}")

    log("INFO", "Estoque reservado", order_id=order_id, produto=produto)
    return {**event, "reserva": {"status": "confirmada", "produto": produto, "quantidade": quantidade}}