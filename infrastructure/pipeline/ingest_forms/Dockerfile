# Build context is the pipeline/ directory (see PipelineStack: from_image_asset
# with directory="../pipeline", file="ingest_forms/Dockerfile"), so COPY paths
# are relative to pipeline/.
FROM public.ecr.aws/lambda/python:3.12

COPY common/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY ingest_forms/app.py ${LAMBDA_TASK_ROOT}/app.py

CMD ["app.handler"]
