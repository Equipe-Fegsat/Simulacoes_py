# Simulações Python – Peabiru | FegSat

Conjunto de ferramentas de simulação e visualização desenvolvidas em Python pela equipe FegSat para o projeto **Peabiru**.

O repositório reúne aplicações para análise da orientação tridimensional e da trajetória estimada do foguete, utilizando dados enviados em tempo real pelo microcontrolador ou registros armazenados em arquivos CSV no cartão SD.

As ferramentas permitem acompanhar o comportamento do sistema de navegação, reproduzir dados de testes anteriores e visualizar graficamente as estimativas produzidas pelo firmware embarcado.

## Visão geral

O repositório possui três simuladores principais:

| Ferramenta | Fonte de dados | Visualização |
|---|---|---|
| **Simulador de rotação ao vivo** | UART do microcontrolador | Orientação 3D e telemetria em tempo real |
| **Simulador de rotação por CSV** | Arquivo CSV do cartão SD | Animação 3D da orientação registrada |
| **Simulador de trajetória** | Arquivo CSV do cartão SD | Trajetória tridimensional do foguete |

### Fluxo de dados

```text
                 ┌─────────────────────┐
                 │    STM32H743        │
                 │  Sistema embarcado  │
                 └──────────┬──────────┘
                            │
                  ┌─────────┴─────────┐
                  │                   │
                UART                 SD Card
                  │                   │
                  ▼                   ▼
          ┌───────────────┐   ┌────────────────┐
          │ Simulador de  │   │ Arquivo CSV    │
          │ rotação ao    │   │ de telemetria  │
          │ vivo          │   └───────┬────────┘
          └───────────────┘           │
                             ┌────────┴─────────┐
                             │                  │
                             ▼                  ▼
                     ┌──────────────┐  ┌────────────────┐
                     │ Simulador de │  │ Simulador de   │
                     │ rotação CSV │  │ trajetória 3D  │
                     └──────────────┘  └────────────────┘
```

## Tecnologias e bibliotecas

As ferramentas foram desenvolvidas em Python e utilizam as seguintes bibliotecas:

| Biblioteca | Aplicação |
|---|---|
| **NumPy** | Operações matemáticas e transformações matriciais |
| **Pandas** | Leitura e tratamento dos arquivos CSV |
| **Matplotlib** | Visualização e animação tridimensional |
| **Plotly** | Gráficos tridimensionais interativos |
| **PySerial** | Comunicação serial com o microcontrolador |
| **Tkinter** | Janelas de seleção de arquivos |

## Instalação e configuração

### Requisitos

- Python 3.10 ou superior.
- macOS, Windows ou Linux.
- VS Code ou outro ambiente de desenvolvimento Python.
- Arquivos CSV gerados pelo firmware para os simuladores offline.
- Conexão USB/serial com o microcontrolador para o simulador ao vivo.

### Criando o ambiente virtual

Na pasta do repositório, execute:

```bash
python3 -m venv .venv
```

Ative o ambiente virtual.

**macOS / Linux:**

```bash
source .venv/bin/activate
```

**Windows:**

```powershell
.venv\Scripts\activate
```

### Instalando as dependências

Com o ambiente virtual ativado:

```bash
python -m pip install --upgrade pip
```

Instale as bibliotecas:

```bash
python -m pip install numpy pandas plotly matplotlib pyserial
```

O Tkinter também é necessário para as janelas de seleção de arquivos. No macOS, verifique sua disponibilidade com:

```bash
python -m tkinter
```

Se uma janela de teste for aberta, o Tkinter está funcionando corretamente.

---

## Simulador de rotação ao vivo

**Arquivo:** `simulador_ao_vivo.py`

### Objetivo

Permitir o acompanhamento da orientação tridimensional do Peabiru em tempo real, recebendo os ângulos estimados pelo firmware através da comunicação serial.

A aplicação representa graficamente a orientação do foguete e apresenta informações de telemetria durante a execução.

### Funcionamento

O programa realiza a leitura contínua dos dados transmitidos pela UART e atualiza a interface gráfica.

Principais recursos:

- Representação tridimensional da orientação do foguete.
- Atualização dos ângulos Roll, Pitch e Yaw.
- Exibição da altitude e da velocidade vertical.
- Indicação da altitude máxima.
- Identificação da fase atual do voo.
- Gráfico com o histórico de altitude.
- Modo de simulação com dados artificiais, sem necessidade de conectar a placa.

A leitura serial é realizada em uma thread separada, permitindo que a interface gráfica continue sendo atualizada enquanto os dados são recebidos.

### Protocolo de comunicação

O firmware deve transmitir uma linha no seguinte formato:

```text
R,<t_ms>,<roll>,<pitch>,<yaw>,<fase>,<altura_m>,<vel_ms>
```

Exemplo:

```text
R,12500,10.5,20.0,35.2,1,45.3,18.7
```

| Campo | Descrição |
|---|---|
| `t_ms` | Tempo em milissegundos |
| `roll` | Ângulo de rotação em torno do eixo X |
| `pitch` | Ângulo de rotação em torno do eixo Y |
| `yaw` | Ângulo de rotação em torno do eixo Z |
| `fase` | Fase atual do voo |
| `altura_m` | Altitude estimada em metros |
| `vel_ms` | Velocidade vertical em m/s |

### Executando

Para iniciar a aplicação:

```bash
python simulador_ao_vivo.py
```

O programa tenta identificar automaticamente uma porta serial compatível. Também é possível informar a porta manualmente:

```bash
python simulador_ao_vivo.py --porta /dev/cu.usbserial-XXXX
```

A taxa de comunicação padrão é 115200 baud.

Para testar a interface sem conectar o microcontrolador:

```bash
python simulador_ao_vivo.py --simular
```

### Parâmetros disponíveis

| Parâmetro | Descrição |
|---|---|
| `--porta` | Define a porta serial |
| `--baud` | Define a velocidade de comunicação |
| `--simular` | Utiliza dados artificiais, sem placa |
| `--dim X Y Z` | Define as dimensões do modelo 3D |
| `--relativo` | Utiliza a primeira orientação como referência |
| `--sem-rastro` | Desativa o rastro do modelo |
| `--janela` | Define o histórico de altitude em segundos |

Exemplo:

```bash
python simulador_ao_vivo.py --simular --dim 1 1 3 --janela 40
```

> **Importante:** feche o Serial Monitor do VS Code ou qualquer outro programa que esteja utilizando a mesma porta serial. Apenas um programa pode acessar a porta por vez.

O arquivo `simulador_rotacao.py` deve permanecer na mesma pasta, pois contém funções geométricas utilizadas pelo simulador ao vivo.

---

## Simulador de rotação por CSV

**Arquivo:** `simulador_rotacao.py`

### Objetivo

Reproduzir a orientação tridimensional estimada pelo sistema embarcado utilizando os dados registrados durante os testes ou voos.

Diferentemente do simulador ao vivo, esta ferramenta não necessita de conexão com o microcontrolador. A reprodução é feita a partir de um arquivo CSV armazenado no cartão SD.

### Funcionamento

O programa lê os ângulos de Euler registrados no arquivo e aplica as transformações matemáticas necessárias para atualizar a orientação do modelo tridimensional.

A convenção de rotação utilizada é:

\[
R=R_z(\psi)R_y(\theta)R_x(\phi)
\]

Onde:

- \(\phi\): Roll.
- \(\theta\): Pitch.
- \(\psi\): Yaw.

As matrizes representam rotações em torno dos eixos Z, Y e X, respectivamente, aplicadas na ordem indicada pelo produto matricial.

### Representação tridimensional

O modelo apresenta:

- Eixo X do corpo em vermelho.
- Eixo Y do corpo em verde.
- Eixo Z do corpo em azul.
- Referencial global em cinza.
- Rastro da extremidade do eixo Z do corpo.

Além da representação 3D, a aplicação apresenta gráficos sincronizados de altitude e velocidade vertical, permitindo acompanhar a orientação e o comportamento do voo ao longo do tempo.

### Executando

Com o ambiente virtual ativado:

```bash
python simulador_rotacao.py
```

Uma janela permitirá selecionar o arquivo CSV.

Também é possível informar diretamente o arquivo:

```bash
python simulador_rotacao.py LOG000.CSV
```

### Parâmetros disponíveis

| Parâmetro | Descrição |
|---|---|
| `--fps` | Taxa de atualização da animação |
| `--vel` | Multiplicador da velocidade de reprodução |
| `--dim X Y Z` | Dimensões do modelo tridimensional |
| `--relativo` | Utiliza a primeira amostra como referência |
| `--sem-rastro` | Desativa o rastro do eixo Z |

Exemplo:

```bash
python simulador_rotacao.py LOG000.CSV --fps 30 --vel 2 --dim 1 1 3
```

Nesse exemplo, a reprodução ocorre com velocidade duas vezes maior que a registrada, utilizando um modelo com proporções de 1 × 1 × 3.

---

## Simulador de trajetória 3D

**Arquivo:** `plot_trajetoria.py`

### Objetivo

Visualizar em três dimensões a trajetória estimada do Peabiru a partir dos dados registrados no cartão SD.

A aplicação utiliza as coordenadas de posição horizontal e altitude para construir um gráfico tridimensional interativo.

### Funcionamento

O programa executa as seguintes etapas:

1. Leitura do arquivo CSV utilizando Pandas.
2. Verificação das colunas necessárias.
3. Conversão e tratamento dos dados numéricos.
4. Organização dos registros em ordem temporal.
5. Separação dos segmentos de acordo com as fases do voo.
6. Identificação do ponto inicial e do apogeu.
7. Construção do gráfico 3D utilizando Plotly.
8. Exportação do gráfico em formato HTML.

### Variáveis utilizadas

| Variável | Descrição |
|---|---|
| `x_m` | Posição estimada no eixo X |
| `y_m` | Posição estimada no eixo Y |
| `alt_m` | Altitude estimada em relação ao ponto de lançamento |
| `fase` | Fase atual do voo |

### Identificação das fases

Cada fase é representada por uma cor:

| Fase | Código | Cor |
|---|---:|---|
| PAD | 0 | Cinza |
| BOOST | 1 | Vermelho |
| COAST | 2 | Laranja |
| DESCENT | 3 | Azul |
| LANDED | 4 | Verde |

O ponto inicial é indicado em preto e o apogeu em roxo.

### Executando

Para iniciar:

```bash
python plot_trajetoria.py
```

Uma janela permitirá selecionar o arquivo CSV.

Também é possível informar o caminho diretamente:

```bash
python plot_trajetoria.py LOG000.CSV
```

### Exportação

Após a leitura do arquivo, o programa salva automaticamente uma versão HTML interativa no mesmo diretório do CSV.

Exemplo:

```text
LOG000.CSV
LOG000_trajetoria.html
```

O arquivo HTML pode ser aberto diretamente em um navegador, permitindo explorar a trajetória sem executar novamente o Python.

### Limitações da estimativa

As posições horizontais X e Y são calculadas por *dead reckoning*, através da integração da aceleração medida pela IMU.

Esse processo acumula erros ao longo do tempo, provocando deriva nas coordenadas horizontais. Portanto, o deslocamento lateral apresentado deve ser interpretado como uma estimativa, e não como uma posição geográfica precisa.

A altitude utiliza as medições do barômetro combinadas com o filtro de Kalman do estimador embarcado, sendo independente da integração horizontal.

---

## Formato dos arquivos CSV

Os simuladores offline utilizam os registros gerados pelo firmware do Peabiru.

Para a visualização completa, o CSV deve conter as colunas correspondentes a cada ferramenta.

| Coluna | Descrição |
|---|---|
| `t_ms` | Tempo desde a inicialização do microcontrolador (ms) |
| `fase` | Estado atual do voo |
| `ax_g`, `ay_g`, `az_g` | Aceleração nos três eixos (g) |
| `gx_dps`, `gy_dps`, `gz_dps` | Velocidade angular nos três eixos (°/s) |
| `press_pa` | Pressão atmosférica (Pa) |
| `alt_m` | Altitude estimada (m) |
| `vel_ms` | Velocidade vertical (m/s) |
| `acc_g` | Módulo da aceleração (g) |
| `tilt_deg` | Inclinação do eixo Z em relação à vertical (°) |
| `x_m`, `y_m` | Posição horizontal estimada (m) |
| `vx_ms`, `vy_ms` | Velocidade horizontal estimada (m/s) |
| `roll_deg`, `pitch_deg`, `yaw_deg` | Ângulos de orientação (°) |
| `acc_up_ms2` | Aceleração vertical sem a gravidade (m/s²) |
| `flight_time_s` | Tempo desde a decolagem (s) |

Os principais campos utilizados por cada ferramenta são:

| Ferramenta | Colunas necessárias |
|---|---|
| Rotação por CSV | `roll_deg`, `pitch_deg`, `yaw_deg` |
| Trajetória 3D | `x_m`, `y_m`, `alt_m`, `fase` |

---

## Limitações conhecidas

- **Deriva horizontal:** as coordenadas X e Y são estimadas por integração da aceleração e acumulam erros ao longo do tempo.
- **Referência do Yaw:** sem magnetômetro, o Yaw não possui referência absoluta ao norte e pode apresentar deriva.
- **Dependência do firmware:** os resultados dependem da calibração dos sensores e do funcionamento do estimador embarcado.
- **Formato do CSV:** os simuladores offline precisam das colunas correspondentes à ferramenta utilizada.
- **Comunicação serial:** o simulador ao vivo depende da disponibilidade da porta serial e do envio correto das mensagens pelo firmware.
- **Visualização não representa validação:** os gráficos apresentam estimativas do sistema, não medições independentes da trajetória real.

As ferramentas são destinadas ao desenvolvimento, análise e validação experimental do sistema de navegação do Peabiru. Seus resultados devem ser comparados com medições externas sempre que possível.

## Estrutura do projeto

```text
Simulacoes_py/
│
├── README.md
│
├── Simulador rotação/
│   ├── simulador_ao_vivo.py
│   └── simulador_rotacao.py
│
└── Simulador trajetória/
    └── plot_trajetoria.py
```

Os scripts podem ser executados individualmente, desde que as dependências estejam instaladas.

## Próximos passos

- [ ] Validar a orientação estimada durante testes físicos.
- [ ] Comparar a trajetória estimada com dados de referência externos.
- [ ] Melhorar a visualização da trajetória e da orientação.
- [ ] Integrar os simuladores em uma interface única.
- [ ] Desenvolver uma interface de análise de telemetria.
- [ ] Avaliar melhorias na estimativa de posição horizontal.

## Equipe

Projeto desenvolvido pela **FegSat**, equipe de nanossatélites da Unesp Guaratinguetá.

**Projeto Peabiru — Ferramentas de simulação e análise de telemetria.**
