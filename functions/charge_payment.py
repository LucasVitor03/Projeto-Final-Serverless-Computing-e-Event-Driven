import json
import boto3
import random
from datetime import datetime, timezone

from aws_xray_sdk.core import patch_all
patch_all()

cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

def log(severity, message, **kwargs):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": "charge-payment",
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
    quantidade = int(event.get("quantidade", 1))

    log("INFO", "Iniciando cobrança", order_id=order_id, cliente=cliente)

    if random.random() < 0.4:
        log("WARNING", "Falha no gateway", order_id=order_id)
        publicar_metrica("RetriesDePagamento", 1)
        raise Exception(f"Falha temporária no gateway para order_id={order_id}")

    valor = quantidade * 29.90
    log("INFO", "Pagamento aprovado", order_id=order_id, valor=valor)
    return {**event, "pagamento": {"status": "aprovado", "valor": valor}}