# Proposta de Infraestrutura: Oracle Cloud Free Tier

Com base nos recursos disponíveis no **Oracle Cloud Always Free** e nos requisitos do **Oracle Hub**, esta é a estratégia recomendada para maximizar performance, segurança e custo-zero.

## 1. Topologia Recomendada

Recomendamos **consolidar** os recursos em uma única instância robusta ("Scale Up") em vez de dividir em várias pequenas ("Scale Out"), pois o overhead de gestão de micro-VMs (1/8 OCPU) não compensa para nossa carga atual.

### 🖥️ Compute (O Coração)
-   **Instância:** **VM.Standard.A1.Flex** (ARM Ampere)
-   **Shape:** **4 OCPUs** e **24 GB RAM** (Usando todo o limite gratuito de uma vez).
-   **Justificativa:** Esta máquina é um "monstro" gratuito. 24GB de RAM permite rodar o Hub, Banco de Dados, VPN, Redis e até Grafana/Prometheus com folga total em memória (In-Memory Processing).
-   **OS:** Ubuntu 22.04 LTS ou Oracle Linux 8/9.

### 💾 Storage (Persistência)
-   **Boot Volume:** 50 GB (Sistema Operacional + Docker Images).
-   **Block Volume (Dados):** **100 GB** montado em `/mnt/oracle_data`.
    -   Aqui ficarão os volumes do Docker (Postgres, Logs, Configs).
    -   *Vantagem:* Se a VM for deletada/recriada, seus dados sobrevivem no volume.
-   **Backup:** Scripts diários enviando dumps criptografados para o **Object Storage** (bucket privado).

### 🛡️ Rede & Segurança (VCN)
-   **Load Balancer (Opcional):** O LB gratuito de 10 Mbps pode ser um gargalo para WebSocket de alta frequência.
    -   *Recomendação:* **Bypass do LB.** Conectar direto na VM via IP Público Reservado (Reserved Public IP).
    -   Usar **Nginx Proxy Manager** ou **Traefik** (container) para gerenciar SSL (HTTPS/WSS) e roteamento interno.
-   **Firewall (Security List):**
    -   `INGRESS TCP 80/443`: Aberto para Web/WebSocket (via Proxy).
    -   `INGRESS UDP 51820`: Aberto para **WireGuard VPN**.
    -   `INGRESS TCP 22 (SSH)`: **FECHADO** para internet. Acesso apenas via IP da VPN (10.x.x.x) ou via Oracle Cloud Shell de emergência.

---

## 2. Containers (Docker Native)

Sim, **containers são essenciais**. A estratégia deve ser **Docker Compose** para orquestrar tudo.
Isso permite atualizar o Hub sem derrubar o Banco, ou reiniciar a VPN sem afetar o Hub.

**Stack Sugerida (`docker-compose.yml`):**

1.  **`proxy` (Nginx Proxy Manager):**
    -   Portas: 80, 443.
    -   Função: Recebe conexões, renova certificados SSL (Let's Encrypt), encaminha `/ws` para o Hub e `/admin` para ferramentas internas.
2.  **`hub` (Oracle Hub):**
    -   Nosso app FastAPI/Python.
    -   Exposto apenas internamente para o Proxy.
3.  **`vpn` (WireGuard / wg-easy):**
    -   Porta: 51820/udp.
    -   Interface Web protegida por senha.
    -   Permite que você acesse o banco de dados e SSH de forma segura do seu PC.
4.  **`db` (PostgreSQL / TimescaleDB - Opcional):**
    -   Para gravar histórico de sinais e usuários.
    -   Persistência no Block Volume.

---

## 3. Estratégia dos Recursos Gratuitos

| Recurso Free Tier | Uso Proposto | Status |
| :--- | :--- | :--- |
| **4 OCPU ARM** | Servidor Principal (Hub + Services) | ✅ Maximizado |
| **24 GB RAM** | Cache Redis + DB em Memória | ✅ Maximizado |
| **200 GB Block** | Persistência de Dados (Docker Vols) | ✅ Uso Inteligente |
| **Autonomous DB** | *Backup Frio* ou Analytics complexo | ⚠️ Reservar (Opcional) |
| **Outbound Data** | 10 TB/mês (Sobra para trading) | ✅ Seguro |

## 4. Veredito

1.  **Containerize tudo.** É a forma limpa de manter o servidor saudável.
2.  **Use a VM ARM de 24GB.** Não desperdice tempo com as micro-VMs AMD.
3.  **VPN no mesmo servidor.** O WireGuard consome recursos mínimos e simplifica a arquitetura (você vira "local" do servidor).
4.  **Esqueça o Load Balancer por enquanto.** Siga com IP direto + Nginx Proxy para latência mínima no WebSocket.

**Próximo Passo Prático:**
Quando formos fazer o deploy, criarei o arquivo `docker-compose.prod.yml` refletindo essa arquitetura.
