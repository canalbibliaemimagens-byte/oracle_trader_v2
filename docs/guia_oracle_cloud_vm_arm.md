# 🚀 Guia de Comandos - Oracle Cloud VM ARM

**Data:** 04/02/2026  
**Objetivo:** Criar e gerenciar VMs ARM na Oracle Cloud para Oracle Trader v2

---

## 📋 Índice

1. [Informações da Infraestrutura](#informações-da-infraestrutura)
2. [Gerenciamento de Scripts](#gerenciamento-de-scripts)
3. [Monitoramento](#monitoramento)
4. [Conexão SSH](#conexão-ssh)
5. [OCI CLI](#oci-cli)
6. [Troubleshooting](#troubleshooting)
7. [Próximos Passos](#próximos-passos)

---

## 🏗️ Informações da Infraestrutura

### IDs Importantes
```bash
COMPARTMENT_ID="ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q"
SUBNET_WS_ID="ocid1.subnet.oc1.sa-saopaulo-1.aaaaaaaa2nlput4rrsnbjw4lztsap673xus4rym2ooqrm6qqrzvta672hglq"
SUBNET_VPN_ID="ocid1.subnet.oc1.sa-saopaulo-1.aaaaaaaaoihuqr5ooazr7y2cpwj53vwjvu7j7r7uazjsmbpnfjvdzsdkjy2q"
VCN_ID="ocid1.vcn.oc1.sa-saopaulo-1.amaaaaaajuxvleia76dwzwb3caz3us7yxuqsdew7uzpadly23tvlkiuu4o6q"
IMAGE_ARM="ocid1.image.oc1.sa-saopaulo-1.aaaaaaaayiprqwic72dwa6teukf4uyd2vqntqvm4cddvvvjcttsn7zn6jsza"
```

### VMs Criadas
- **VM x86 (ativa):** `vm-websocket` - IP: 163.176.208.248
- **VM ARM (tentando criar):** `vm-arm-ideal-4c24g` ou `vm-arm-fallback-1c6g`

### Recursos Free Tier
```
ARM (VM.Standard.A1.Flex):
├─ 4 OCPUs total
├─ 24 GB RAM total
└─ Distribuição livre

x86 (VM.Standard.E2.1.Micro):
├─ 2 VMs disponíveis
├─ 1 vCPU cada
└─ 1 GB RAM cada

Block Storage:
└─ 200 GB total gratuito
```

---

## 🤖 Gerenciamento de Scripts

### Ver Scripts Rodando
```bash
# Listar todos os scripts de criação de VM
ps aux | grep criar_vm_arm

# Ver PIDs e consumo de recursos
top -p $(pgrep -d',' -f criar_vm_arm)
```

### Parar Scripts
```bash
# Parar todos os scripts
pkill -f criar_vm_arm

# Parar script específico
pkill -f criar_vm_arm_ideal.sh
pkill -f criar_vm_arm_fallback.sh

# Parar por PID específico
kill <PID>
```

### Reiniciar Scripts
```bash
# Dual strategy (ideal + fallback)
nohup ~/criar_vm_arm_ideal.sh > ~/vm_arm_ideal.log 2>&1 &
nohup ~/criar_vm_arm_fallback.sh > ~/vm_arm_fallback.log 2>&1 &

# Verificar se iniciaram
ps aux | grep criar_vm_arm
```

### Localização dos Scripts
```bash
~/criar_vm_arm_ideal.sh      # 4 OCPU + 24GB
~/criar_vm_arm_fallback.sh   # 1 OCPU + 6GB
~/criar_vm_arm.sh            # Script antigo (descontinuado)
```

---

## 📊 Monitoramento

### Ver Logs em Tempo Real
```bash
# Acompanhar IDEAL
tail -f ~/vm_arm_ideal.log

# Acompanhar FALLBACK
tail -f ~/vm_arm_fallback.log

# Ambos simultaneamente (atualiza a cada 10s)
watch -n 10 'tail -3 ~/vm_arm_ideal.log; echo "---"; tail -3 ~/vm_arm_fallback.log'

# Sair do watch/tail
# Pressione Ctrl+C
```

### Ver Últimas Linhas dos Logs
```bash
# Últimas 20 linhas
tail -20 ~/vm_arm_ideal.log
tail -20 ~/vm_arm_fallback.log

# Últimas 5 linhas de ambos
echo "=== IDEAL ===" && tail -5 ~/vm_arm_ideal.log
echo "=== FALLBACK ===" && tail -5 ~/vm_arm_fallback.log
```

### Estatísticas
```bash
# Contar tentativas
grep -c "Tentativa #" ~/vm_arm_ideal.log
grep -c "Tentativa #" ~/vm_arm_fallback.log

# Ver se algum conseguiu criar
grep "SUCESSO" ~/vm_arm_*.log

# Ver últimas 10 tentativas com horário
grep "Tentativa #" ~/vm_arm_ideal.log | tail -10
grep "Tentativa #" ~/vm_arm_fallback.log | tail -10

# Ver erros
grep "Erro" ~/vm_arm_*.log
grep "Out of host capacity" ~/vm_arm_*.log | wc -l
```

### Tamanho dos Logs
```bash
# Ver tamanho dos arquivos de log
ls -lh ~/vm_arm_*.log

# Limpar logs se ficarem muito grandes
> ~/vm_arm_ideal.log
> ~/vm_arm_fallback.log
```

---

## 🔐 Conexão SSH

### Conectar nas VMs

#### VM x86 (atual - 163.176.208.248)
```bash
# Do seu PC local
ssh -i ~/.ssh/oracle_new ubuntu@163.176.208.248

# Do Cloud Shell
ssh -i ~/.ssh/id_rsa ubuntu@163.176.208.248
```

#### VM ARM (quando criada)
```bash
# Descobrir IP da VM ARM criada
~/bin/oci compute instance list \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --all \
  --query "data[?\"lifecycle-state\"=='RUNNING'].{Name:\"display-name\",IP:\"public-ip\",Shape:shape}" \
  --output table

# Conectar (substitua <IP> pelo IP real)
ssh -i ~/.ssh/oracle_new ubuntu@<IP>
```

### Forçar Desconexão SSH Travada
```bash
# Sequência de escape (mais rápido)
Enter + ~ + .

# Ou matar processo SSH (outro terminal)
pkill -9 ssh
pkill -9 -f "163.176.208.248"
```

### Copiar Chaves SSH
```bash
# Do Cloud Shell para seu PC
# 1. No Cloud Shell:
cat ~/.ssh/id_rsa

# 2. No seu PC:
nano ~/.ssh/oracle_arm_key
# Cole o conteúdo, salve (Ctrl+O, Enter, Ctrl+X)

# 3. Ajustar permissões
chmod 600 ~/.ssh/oracle_arm_key
```

---

## ⚙️ OCI CLI

### Comandos Básicos
```bash
# Ver versão
~/bin/oci --version

# Testar autenticação
~/bin/oci iam region list --output table

# Ver regiões subscritas
~/bin/oci iam region-subscription list \
  --tenancy-id ocid1.tenancy.oc1..aaaaaaaatazgsfir6ubuf7uknf53ay4wnr37bwv7yedbdlofywgattc5bsoq \
  --output table
```

### Gerenciar VMs
```bash
# Listar todas as VMs
~/bin/oci compute instance list \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --all \
  --output table

# Ver apenas VMs rodando
~/bin/oci compute instance list \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --lifecycle-state RUNNING \
  --output table

# Detalhes de uma VM específica
~/bin/oci compute instance get \
  --instance-id <INSTANCE_ID>

# Parar VM
~/bin/oci compute instance action \
  --instance-id <INSTANCE_ID> \
  --action STOP \
  --wait-for-state STOPPED

# Iniciar VM
~/bin/oci compute instance action \
  --instance-id <INSTANCE_ID> \
  --action START \
  --wait-for-state RUNNING

# Reiniciar VM
~/bin/oci compute instance action \
  --instance-id <INSTANCE_ID> \
  --action SOFTRESET

# Deletar VM
~/bin/oci compute instance terminate \
  --instance-id <INSTANCE_ID> \
  --force
```

### Criar VM ARM Manualmente
```bash
# IDEAL: 4 OCPU + 24GB
~/bin/oci compute instance launch \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --availability-domain "PBZu:SA-SAOPAULO-1-AD-1" \
  --shape "VM.Standard.A1.Flex" \
  --shape-config '{"ocpus": 4, "memoryInGBs": 24}' \
  --display-name "vm-oracle-trader-manual" \
  --image-id ocid1.image.oc1.sa-saopaulo-1.aaaaaaaayiprqwic72dwa6teukf4uyd2vqntqvm4cddvvvjcttsn7zn6jsza \
  --subnet-id ocid1.subnet.oc1.sa-saopaulo-1.aaaaaaaa2nlput4rrsnbjw4lztsap673xus4rym2ooqrm6qqrzvta672hglq \
  --assign-public-ip true \
  --boot-volume-size-in-gbs 50 \
  --ssh-authorized-keys-file ~/.ssh/authorized_keys

# FALLBACK: 1 OCPU + 6GB
~/bin/oci compute instance launch \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --availability-domain "PBZu:SA-SAOPAULO-1-AD-1" \
  --shape "VM.Standard.A1.Flex" \
  --shape-config '{"ocpus": 1, "memoryInGBs": 6}' \
  --display-name "vm-oracle-trader-manual" \
  --image-id ocid1.image.oc1.sa-saopaulo-1.aaaaaaaayiprqwic72dwa6teukf4uyd2vqntqvm4cddvvvjcttsn7zn6jsza \
  --subnet-id ocid1.subnet.oc1.sa-saopaulo-1.aaaaaaaa2nlput4rrsnbjw4lztsap673xus4rym2ooqrm6qqrzvta672hglq \
  --assign-public-ip true \
  --boot-volume-size-in-gbs 50 \
  --ssh-authorized-keys-file ~/.ssh/authorized_keys
```

### Buscar Imagens
```bash
# Listar imagens Ubuntu ARM disponíveis
~/bin/oci compute image list \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --operating-system "Canonical Ubuntu" \
  --shape "VM.Standard.A1.Flex" \
  --sort-by TIMECREATED \
  --sort-order DESC \
  --limit 5 \
  --output table

# Listar imagens x86
~/bin/oci compute image list \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --operating-system "Canonical Ubuntu" \
  --shape "VM.Standard.E2.1.Micro" \
  --sort-by TIMECREATED \
  --sort-order DESC \
  --limit 5 \
  --output table
```

---

## 🔧 Troubleshooting

### Verificar Recursos Disponíveis na VM
```bash
# Memória
free -h

# Disco
df -h

# CPU
lscpu
nproc

# Processos consumindo recursos
top
htop  # Se instalado
```

### Verificar Conectividade
```bash
# Ping externo
ping -c 4 8.8.8.8

# Testar DNS
nslookup google.com

# Ver interfaces de rede
ip addr show

# Ver rotas
ip route show
```

### Logs do Sistema
```bash
# Logs gerais
sudo journalctl -xe

# Logs de boot
sudo journalctl -b

# Logs SSH
sudo tail -50 /var/log/auth.log
```

### Espaço em Disco
```bash
# Ver uso detalhado
du -h --max-depth=1 ~ | sort -hr

# Limpar apt cache
sudo apt clean
sudo apt autoclean
sudo apt autoremove

# Limpar logs antigos
sudo journalctl --vacuum-time=7d
```

### Problemas Comuns

#### "Out of host capacity"
```
Problema: Não há recursos ARM disponíveis
Solução: Scripts continuam tentando automaticamente
Dica: Madrugada (2h-6h) tem mais disponibilidade
```

#### "Permission denied (publickey)"
```
Problema: Chave SSH incorreta
Solução: 
1. Verificar caminho da chave: ls -la ~/.ssh/
2. Usar chave correta: ssh -i ~/.ssh/oracle_new ubuntu@<IP>
3. Verificar permissões: chmod 600 ~/.ssh/oracle_new
```

#### "Connection refused"
```
Problema: VM não está rodando ou firewall bloqueando
Solução:
1. Verificar se VM está RUNNING
2. Verificar Security List (porta 22 aberta)
3. Verificar firewall interno da VM
```

#### Scripts não estão rodando
```
Problema: Scripts foram mortos
Solução: Reiniciar scripts:
nohup ~/criar_vm_arm_ideal.sh > ~/vm_arm_ideal.log 2>&1 &
nohup ~/criar_vm_arm_fallback.sh > ~/vm_arm_fallback.log 2>&1 &
```

---

## 📝 Próximos Passos (Quando VM ARM Criada)

### 1. Conectar na VM ARM
```bash
ssh -i ~/.ssh/oracle_new ubuntu@<IP_DA_VM_ARM>
```

### 2. Configurar Ambiente Python
```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Python e dependências
sudo apt install -y python3.11 python3-pip python3-venv git

# Criar ambiente virtual
python3 -m venv ~/oracle_env
source ~/oracle_env/bin/activate

# Instalar dependências do projeto
pip install --upgrade pip
pip install numpy pandas stable-baselines3 hmmlearn websockets supabase python-dotenv
```

### 3. Clonar Projeto
```bash
cd ~
git clone https://github.com/canalbibliaemimagens-byte/oracle_trader_v2
cd oracle_trader_v2
```

### 4. Configurar WebSocket IPC
```bash
# Criar estrutura
mkdir -p infra/websocket

# Implementar servidor, protocolo e cliente
# (Seguir arquitetura em docs/ARCH_V2_HIGH_AVAILABILITY.md)
```

### 5. Testar Inferência
```bash
# Baixar modelos treinados (do Kaggle)
# Testar inferência com dados de exemplo
# Validar latência (<50ms)
```

---

## 🎯 Estratégia Atual

### Dual Strategy Ativa
```
Script 1 (IDEAL): 4 OCPU + 24GB + 50GB disco
├─ Probabilidade: ~5-10% (muito disputado)
├─ Tempo estimado: 1-3 semanas
└─ Log: ~/vm_arm_ideal.log

Script 2 (FALLBACK): 1 OCPU + 6GB + 50GB disco
├─ Probabilidade: ~60-70% (mais realista)
├─ Tempo estimado: 2-7 dias
└─ Log: ~/vm_arm_fallback.log

Funcionamento:
├─ Ambos tentam a cada 5 minutos
├─ Quando um conseguir, mata o outro automaticamente
└─ Você recebe a VM criada
```

### Horários com Mais Disponibilidade
```
🟢 Melhor: 2h-6h da madrugada (horário Brasil)
🟡 Médio: Fins de semana / Feriados
🔴 Pior: Horário comercial (9h-18h)
```

---

## 📞 Suporte

### Links Úteis
- **Oracle Cloud Console:** https://cloud.oracle.com
- **Documentação OCI:** https://docs.oracle.com/iaas/
- **Fóruns Oracle:** https://community.oracle.com
- **Reddit r/oraclecloud:** https://reddit.com/r/oraclecloud

### Informações da Conta
- **Tenancy:** cerucci
- **Home Region:** GRU (sa-saopaulo-1)
- **Compartment:** websocket-server
- **Email:** cerucci@gmail.com

---

## 🚨 Comandos de Emergência

### Verificar se Scripts Estão Rodando
```bash
# Status rápido
ps aux | grep criar_vm_arm | grep -v grep

# Se não mostrar nada, reiniciar:
cd ~
nohup ~/criar_vm_arm_ideal.sh > ~/vm_arm_ideal.log 2>&1 &
nohup ~/criar_vm_arm_fallback.sh > ~/vm_arm_fallback.log 2>&1 &
```

### Verificar se Conseguiu Criar VM
```bash
# Checar logs
grep "SUCESSO" ~/vm_arm_*.log

# Listar VMs ARM
~/bin/oci compute instance list \
  --compartment-id ocid1.compartment.oc1..aaaaaaaau54kfd6weobmsrbvc4zi6c6pf34kdnu4tobhlwb4zt2mujxhsg2q \
  --all | grep -A 5 "vm-arm"
```

### Backup dos Scripts
```bash
# Fazer backup dos scripts
cp ~/criar_vm_arm_ideal.sh ~/criar_vm_arm_ideal.sh.backup
cp ~/criar_vm_arm_fallback.sh ~/criar_vm_arm_fallback.sh.backup

# Restaurar se necessário
cp ~/criar_vm_arm_ideal.sh.backup ~/criar_vm_arm_ideal.sh
```

---

**Última atualização:** 04/02/2026 06:30  
**Versão:** 1.0  
**Autor:** Claude + Cerucci

---

## 📌 Notas Importantes

1. **Scripts rodam 24/7**: Não precisa manter terminal aberto
2. **Disco mínimo (50GB)**: Pode expandir depois anexando Block Volumes
3. **Dual strategy**: Aumenta chances de conseguir VM ARM
4. **Paciência**: Pode levar dias/semanas, mas a maioria consegue
5. **Horário**: Madrugada (2h-6h) tem mais sucesso segundo fóruns
6. **Região única**: Conta Free Tier permite apenas 1 região (GRU)
7. **Desenvolvimento local**: Continue desenvolvendo enquanto aguarda VM

**Boa sorte! 🍀**
