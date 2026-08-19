# Build context: pipeline/ . Bundles the thin-mode oracledb client.
FROM public.ecr.aws/lambda/python:3.12

COPY common/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY ingest_plsql/app.py ${LAMBDA_TASK_ROOT}/app.py

CMD ["app.handler"]
