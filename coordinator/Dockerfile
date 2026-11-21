FROM python:3.12-slim
RUN useradd --uid 10000 --no-create-home coordinator \
    && mkdir /logs && chown coordinator /logs
WORKDIR /app
COPY coordinator.py ask.py policy.json ./
USER coordinator
EXPOSE 8000
CMD ["python", "-u", "coordinator.py"]
