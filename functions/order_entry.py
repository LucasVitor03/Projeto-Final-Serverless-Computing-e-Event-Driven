import json
import boto3
import os
import uuid
from datetime import datetime, timezone

from aws_xray_sdk.core import patch_all
patch_all()

sfn = boto3.client("stepfunctions", region_name="us-east-1")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN")

def log(severity, message, **kwargs):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": "order-entry",
        "message": message,
        **kwargs
    }))

def handler(event, context):
    # Suporte a CORS para o frontend no S3
    headers = {
        "Content-Type": "application/json",
    }

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "headers": headers,
                "body": json.dumps({"erro": "Body inválido"})}

    produto = body.get("produto")
    quantidade = body.get("quantidade")
    cliente = body.get("cliente")

    if not all([produto, quantidade, cliente]):
        return {"statusCode": 400, "headers": headers,
                "body": json.dumps({"erro": "Campos obrigatórios: produto, quantidade, cliente"})}

    order_id = str(uuid.uuid4())

    log("INFO", "Pedido recebido", order_id=order_id,
        cliente=cliente, produto=produto, quantidade=quantidade)

    sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=f"pedido-{order_id}",
        input=json.dumps({
            "order_id": order_id,
            "produto": produto,
            "quantidade": int(quantidade),
            "cliente": cliente
        })
    )

    log("INFO", "Execução iniciada no Step Functions", order_id=order_id)

    return {
        "statusCode": 202,
        "headers": headers,
        "body": json.dumps({
            "mensagem": "Pedido recebido e em processamento",
            "order_id": order_id
        })
    }