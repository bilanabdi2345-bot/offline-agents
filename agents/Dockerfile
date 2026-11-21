FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home agent \
    && mkdir /notes && chown agent /notes
WORKDIR /app
COPY agent.py check_walls.py ./
USER agent
EXPOSE 9000
CMD ["python", "-u", "agent.py"]
