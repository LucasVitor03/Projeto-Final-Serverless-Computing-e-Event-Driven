import json
import boto3
from datetime import datetime, timezone, timedelta

from aws_xray_sdk.core import patch_all
patch_all()

cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")
logs_client = boto3.client("logs", region_name="us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def log(severity, message, **kwargs):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": "ai-analyzer",
        "message": message,
        **kwargs
    }))

def coletar_metricas():
    # Coleta métricas customizadas dos últimos 30 minutos
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(minutes=30)

    metricas = {}
    for nome in ["PedidosNaDLQ", "PedidosAprovados", "RetriesDePagamento"]:
        try:
            resp = cloudwatch.get_metric_statistics(
                Namespace="OrderPipeline",
                MetricName=nome,
                StartTime=inicio,
                EndTime=agora,
                Period=1800,
                Statistics=["Sum"]
            )
            valor = resp["Datapoints"][0]["Sum"] if resp["Datapoints"] else 0
            metricas[nome] = valor
        except Exception:
            metricas[nome] = 0

    return metricas

def coletar_logs_recentes(log_group, limite=10):
    # Coleta os logs mais recentes de um log group
    try:
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=1
        )
        if not streams["logStreams"]:
            return []

        stream_name = streams["logStreams"][0]["logStreamName"]
        eventos = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            limit=limite
        )
        return [e["message"] for e in eventos["events"]]
    except Exception as e:
        return [f"Erro ao coletar logs: {str(e)}"]

def coletar_estado_alarme():
    try:
        resp = cloudwatch.describe_alarms(
            AlarmNames=["order-pipeline-final-pedidos-na-dlq"]
        )
        if resp["MetricAlarms"]:
            return resp["MetricAlarms"][0]["StateValue"]
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"

def handler(event, context):
    # Extrai a mensagem da DLQ
    for record in event.get("Records", []):
        try:
            body = json.loads(record.get("body", "{}"))
        except Exception:
            body = {"raw": record.get("body", "")}

        order_id = body.get("order_id", "desconhecido")
        erro = body.get("erro", body.get("Cause", "erro não especificado"))

        log("INFO", "Analisando falha com IA", order_id=order_id)

        # Coleta o pacote de evidências do CloudWatch
        metricas = coletar_metricas()
        logs_reserve = coletar_logs_recentes("/aws/lambda/order-pipeline-final-reserve-stock")
        logs_payment = coletar_logs_recentes("/aws/lambda/order-pipeline-final-charge-payment")
        estado_alarme = coletar_estado_alarme()

        # Monta o pacote de contexto para a IA
        contexto = f"""
Você é um especialista em AIOps analisando uma falha em um pipeline serverless de pedidos na AWS.

FALHA DETECTADA:
- Order ID: {order_id}
- Erro: {erro}
- Timestamp: {datetime.now(timezone.utc).isoformat()}

EVIDÊNCIAS DO CLOUDWATCH:

Métricas (últimos 30 minutos):
- PedidosNaDLQ: {metricas.get('PedidosNaDLQ', 0)}
- PedidosAprovados: {metricas.get('PedidosAprovados', 0)}
- RetriesDePagamento: {metricas.get('RetriesDePagamento', 0)}

Estado do Alarme: {estado_alarme}

Logs recentes do reserve-stock:
{chr(10).join(logs_reserve[:5])}

Logs recentes do charge-payment:
{chr(10).join(logs_payment[:5])}

Com base nessas evidências, forneça:
1. DIAGNÓSTICO: qual é o problema e por que aconteceu
2. CAUSA PROVÁVEL: a causa raiz técnica
3. IMPACTO: quantos pedidos foram afetados e qual o risco
4. RECOMENDAÇÃO: ação técnica concreta para resolver e prevenir
Seja objetivo e técnico. Máximo de 200 palavras.
"""

        # Chama o Bedrock com o modelo Amazon Titan
        try:
            resposta = bedrock.invoke_model(
                modelId="amazon.titan-text-express-v1",
                body=json.dumps({
                    "inputText": contexto,
                    "textGenerationConfig": {
                        "maxTokenCount": 500,
                        "temperature": 0.3
                    }
                }),
                contentType="application/json",
                accept="application/json"
            )

            resultado = json.loads(resposta["body"].read())
            analise = resultado["results"][0]["outputText"]

            log("INFO", "Análise AIOps concluída",
                order_id=order_id,
                estado_alarme=estado_alarme,
                metricas=metricas,
                analise_ia=analise)

        except Exception as e:
            log("ERROR", "Erro ao chamar Bedrock",
                order_id=order_id, erro=str(e))