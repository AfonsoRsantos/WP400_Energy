# Energy Monitor — Wago 762-3405
## Dashboard Modbus TCP para Multimedidor de Energia

---

## Estrutura dos arquivos

```
energy-monitor/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── build.sh
├── app/
│   ├── server.py          ← API Flask + poller Modbus
│   └── modbus_reader.py   ← Cliente Modbus TCP puro (sem lib externa)
└── templates/
    └── index.html         ← Dashboard web completo
```

---

## Grandezas mapeadas (FC3, Unit ID 1)

| Endereço | Grandeza            | Unidade |
|----------|---------------------|---------|
| 2        | Corrente L1         | A       |
| 3        | Corrente L2         | A       |
| 4        | Corrente L3         | A       |
| 5        | Tensão L1           | V       |
| 6        | Tensão L2           | V       |
| 7        | Tensão L3           | V       |
| 8        | Potência Ativa Total| kW      |
| 9        | Potência Reativa    | kVAr    |
| 10       | Potência Aparente   | kVA     |
| 11       | Frequência          | Hz      |
| 12       | Fator de Potência L1| —       |
| 13       | Fator de Potência L2| —       |
| 14       | Fator de Potência L3| —       |

> **Scaling padrão:** registros de corrente/tensão/potência ÷ 10 | FP ÷ 1000
> Ajuste a função `parse_value()` em `modbus_reader.py` se necessário.

---

## INSTALAÇÃO NA IHM WAGO 762-3405

### Opção A — Build na própria IHM (recomendado se tiver acesso à internet)

```bash
# 1. Copie os arquivos para a IHM via SCP ou USB
scp -r energy-monitor/ admin@<IP_IHM>:/home/admin/

# 2. Conecte via SSH
ssh admin@<IP_IHM>

# 3. Entre na pasta
cd /home/admin/energy-monitor

# 4. Construa a imagem (pode demorar ~3-5 min)
docker build --platform linux/arm64 -t energy-monitor:latest .

# 5. Inicie o container
docker run -d \
  --name energy-monitor \
  --restart unless-stopped \
  -p 8080:5000 \
  -e MODBUS_HOST=<IP_DO_MEDIDOR> \
  -e MODBUS_PORT=502 \
  -e MODBUS_UNIT_ID=1 \
  -e POLL_INTERVAL=2.0 \
  energy-monitor:latest
```

---

### Opção B — Build no PC e transferência para a IHM (sem internet na IHM)

```bash
# ── No seu PC (com Docker e buildx instalados) ──

# 1. Habilite o builder multi-plataforma (apenas uma vez)
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap

# 2. Construa a imagem para ARM64 e exporte
cd energy-monitor/
docker buildx build \
  --platform linux/arm64 \
  --output type=docker,name=energy-monitor:latest \
  .

# 3. Exporte para arquivo .tar.gz
docker save energy-monitor:latest | gzip > energy-monitor.tar.gz

# 4. Transfira para a IHM
scp energy-monitor.tar.gz admin@<IP_IHM>:/home/admin/

# ── Na IHM (via SSH) ──
ssh admin@<IP_IHM>

# 5. Importe a imagem
gunzip -c energy-monitor.tar.gz | docker load

# 6. Inicie o container
docker run -d \
  --name energy-monitor \
  --restart unless-stopped \
  -p 8080:5000 \
  -e MODBUS_HOST=<IP_DO_MEDIDOR> \
  -e MODBUS_PORT=502 \
  -e MODBUS_UNIT_ID=1 \
  -e POLL_INTERVAL=2.0 \
  energy-monitor:latest
```

---

### Opção C — Docker Compose (mais fácil de gerenciar)

```bash
# Copie a pasta completa para a IHM, depois:
ssh admin@<IP_IHM>
cd /home/admin/energy-monitor

# Edite o IP do medidor no docker-compose.yml
nano docker-compose.yml
# → altere: MODBUS_HOST=192.168.1.100

# Suba o serviço
docker-compose up -d

# Verifique os logs
docker-compose logs -f
```

---

## ACESSO AO DASHBOARD

Abra no navegador:
```
http://<IP_DA_IHM>:8080
```

---

## Comandos úteis

```bash
# Ver logs em tempo real
docker logs -f energy-monitor

# Parar o container
docker stop energy-monitor

# Remover o container
docker rm energy-monitor

# Reiniciar
docker restart energy-monitor

# Ver uso de recursos
docker stats energy-monitor
```

---

## Ajuste de escala dos registros

Se os valores aparecerem errados, edite `app/modbus_reader.py`:

```python
# Linha com parse_value — o segundo argumento é o divisor
"corrente_L1": parse_value(regs[0], 10.0),   # raw / 10 → ex: 150 → 15.0 A
"tensao_L1":   parse_value(regs[3], 10.0),   # raw / 10 → ex: 2200 → 220.0 V
"fp_L1":       parse_value(regs[10], 1000.0) # raw / 1000 → ex: 950 → 0.950
```

Consulte o manual do seu multimedidor para confirmar o fator de escala.

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|---------------|---------|
| Dashboard mostra "DESCONECTADO" | IP errado ou firewall | Verifique `MODBUS_HOST` e a rede |
| Valores zerados ou absurdos | Fator de escala errado | Ajuste `parse_value()` em `modbus_reader.py` |
| Porta 8080 inacessível | Firewall da IHM | Libere a porta 8080 no firewall |
| Container não inicia | Imagem incompatível | Certifique que usou `--platform linux/arm64` |
