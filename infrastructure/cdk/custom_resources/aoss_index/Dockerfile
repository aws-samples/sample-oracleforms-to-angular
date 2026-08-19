# AOSS vector-index creator (CloudFormation custom resource).
# Build context is this directory (DockerImageCode.from_image_asset).
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY index.py ${LAMBDA_TASK_ROOT}/index.py

CMD ["index.handler"]
