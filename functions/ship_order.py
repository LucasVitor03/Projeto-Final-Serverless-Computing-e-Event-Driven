import json
import boto3
from datetime import datetime, timezone

from aws_xray_sdk.core import patch_all
patch_all()

cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

def log(severity, message, **kwargs):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": "ship-order",
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
    cliente = event.get("cliente")
    produto = event.get("produto")
    timestamp = datetime.now(timezone.utc).isoformat()

    log("INFO", "Despachando pedido", order_id=order_id,
        cliente=cliente, produto=produto)

    publicar_metrica("PedidosAprovados", 1)

    log("INFO", "Pedido despachado", order_id=order_id, timestamp=timestamp)

    return {**event, "envio": {
        "status": "despachado",
        "timestamp": timestamp,
        "previsao_entrega": "3 dias uteis"
    }}