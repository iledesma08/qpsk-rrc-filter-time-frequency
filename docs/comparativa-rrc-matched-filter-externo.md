# Comparativa: proyecto QPSK-RRC local (tiempo vs frecuencia) vs `IshaanParikh/rrc-matched-filter`

> Non-normative external reference. Informative context only — never a requirement source. Normative decisions live in `docs/contracts/`; our AWGN/Ber policy is `docs/contracts/link-awgn-annex-35.md` (dormant annex, never DoD).

> Fecha: 2026-09-23. Fuentes primarias locales: `CONTEXT.md`, `README.md`, `docs/plan-gantt.md`, `docs/contracts/*.md` (13–19), `docs/adr/0001–0006`. Fuente externa: https://github.com/IshaanParikh/rrc-matched-filter (`README.md`, `python/dsp_common.py`, `python/gen_stimulus.py`, `python/golden_model.py`, `rtl/rrc_fir_core.v`, `rtl/rrc_fir_axis.v`, `rtl/booth_mult_r4.v`, `rtl/pipelined_adder_tree.v`, `rtl/rrc_coeff_rom.v`, `sim/run_sim.sh`, `syn/rrc_fir.sdc`, `syn/build.tcl`).

## 1. Idea en una línea

| | Local (este repo) | Externo (`IshaanParikh/rrc-matched-filter`) |
|---|---|---|
| Objetivo | Ejercicio didáctico **tiempo vs frecuencia + serial vs optimizado + PPA** con 4 personas, slides y Gantt. | Receptor QPSK real: **filtro RRC adaptado (matched) verificado por BER/EVM/ojo**, no por contraste de dominios. |
| Lema | “Mejor trade-off PPA, no un solo eje” (`CONTEXT.md:92-94`, `docs/contracts/ppa-matrix-18.md`). | “Un filtro puede coincidir con su modelo y aun así ser el filtro equivocado; BER 1.10× teoría lo prueba” (README externo). |

## 2. Parámetros del filtro

| Característica | Local | Externo |
|---|---|---|
| Tipo | RRC conformación, energía unitaria `sum(h²)=1` (`docs/contracts/rrc-coefficient-contract-13.md:110-156`) | RRC adaptado Rx, energía unitaria `h/sqrt(sum(h²))` (`python/dsp_common.py:20-52`) |
| Roll-off | **α=0.5 fijo** por consigna (`CONTEXT.md:19-25`) | **β=0.35 por defecto** (`--beta`, `python/gen_stimulus.py:64`) |
| Oversampling | **2×** (`T/2`, 2 muestras/símbolo) (`CONTEXT.md:15-17`) | **4×** (`--sps`, 4 muestras/símbolo) |
| N.º taps | **8** (`CONTEXT.md:27-29`, `AGENTS.md:23`) | **33** (`span*sps+1 = 8*4+1`, `rtl/rrc_fir_core.v:21`, `dsp_common.py:29`) |
| Span / grilla | `t[n]=(n-3.5)/2`, `[-1.75…+1.75]·T`, retardo `D=3.5 muestras=1.75T` (`rrc-coefficient-contract-13.md:20-25,96-106`) | Span **8 símbolos**, retardo **16 por filtro**, pico en `k*sps+(N-1)` TX+RX (`gen_stimulus.py:167-169`) |
| Coeficientes | crudos `[0.0154,-0.1568,…]` → normalizados `[0.0109,-0.1109,0.1109,0.6893,…]`, `sum=1.4006`, `max=0.689<1`; se rechazó DC-unidad (`rrc-coefficient-contract-13.md:110-156,405-412`) | 33 simétricos lineales, plot float vs Q1.15 + err ±0.5LSB (`docs/rrc_taps.png`) |
| Fórmula | RRC discreta en grilla 2× (contrato 13) | RRC cerrada con manejo `t=0` y `t=±1/(4β)` (`dsp_common.py:32-47`) |

Consecuencia: **no son intercambiables**. El local es corto (8 taps, barato para explorar 12 filas PPA y FFT16); el externo es largo (33 taps, más selectivo, pensado para ganancia de filtrado adaptado).

## 3. Modulación / estímulo / canal

| | Local | Externo |
|---|---|---|
| QPSK | `±1±j`, `I,Q∈{+1,-1}`, `idx→{0:+1+j,1:+1-j,2:-1+j,3:-1-j}` (`CONTEXT.md:7-9`, `qpsk-stimulus-15.md:140-144`) | Gray `((1-2b0)+j(1-2b1))/√2` (`gen_stimulus.py:88-89`) |
| Frame | **1024 símbolos** (40 fijos edge + 984 aleat `default_rng(2026)`), 5 patrones de 8 símbolos (`qpsk-stimulus-15.md:18-36`) | **4096 símbolos → 16384 muestras** por defecto, seed `0xB0071` (`gen_stimulus.py:61,67,73`) |
| Upsampling | Inserción de ceros `x[2k]=s[k]`, `L=2048` in → `2055` out causal `y[n]=Σh[m]x[n-m]`; RTL **sin** upsampler (`qpsk-stimulus-15.md:146-162`) | Zero-stuff sps → **TX RRC (conv truncada) → AWGN → escala/headroom → Q1.15 → .hex** (`gen_stimulus.py:91-107`) |
| Canal | **Sin ruido** (comparación exacta float/fxp/RTL); centros `2k+3.5` sin muestra al centro (`qpsk-stimulus-15.md:161,240-249`) | **Con AWGN `Es/N0=8dB`** + `headroom 0.92/0.95` percentil 99.99 (`gen_stimulus.py:69-72,109-122`) |
| Foco verificación | Igualdad numérica | Calidad de enlace (BER/EVM/ojo) |

## 4. Dominios y arquitecturas

| | Local | Externo |
|---|---|---|
| Tiempo | Convolución directa `muestra×coef` (`CONTEXT.md:31-33`) | **Único dominio**: FIR directo `línea 33 + 33 Booth + árbol` (`rrc_fir_core.v:1-16`) |
| Frecuencia | **Sí**: `FFT16→×→IFFT` OLS forzado-50% `N=16,H=8`, `h16=[h,zeros(8)]`, descarta `z[0:8]`, emite `z[8:16]`; pre-frame ceros; NumPy sin escala fwd, `1/N` inv (`frequency-block-contract-14.md:17-48,101-139,204-232`) | **No**: sin FFT/OLA |
| Serial | **Sí, punto de partida**: 1 muestra/ciclo, 1 MAC, `SPC=1`, `S=1→II=8` (`ready_o` cae 7/8) (`CONTEXT.md:79-86`, `rtl-streaming-17.md:28-29,94-108`) | **No**: directamente **totalmente paralelo/unfolded**, 1 beat/ciclo, latencia 12 |
| Optimizado | Tiempo `pipeline+sistólico S=2,4,8×P=1,2` (6 filas); frec `unfolded U=2,4,8 + folded F=2` sobre `U8`; una fuente parametrizada bit-exacta (`ppa-matrix-18.md:21-25,157-218`) | Equivalente a fila `S=33` local: 33 `booth_mult_r4` en paralelo + `pipelined_adder_tree 33→17→9→5→3→2→1` (6 etapas), dual I/Q en paralelo (`rrc_fir_core.v:72-91`, `rrc_fir_axis.v`) |

## 5. Punto fijo y SQNR

| | Local | Externo |
|---|---|---|
| Formato | **Ancho común `Q2.(W-2)`** datos+coefs, `[-2,+2)`, `+1/-1` exactos; a `W=16`: `[179,-1818,1818,11295,…]` (`fxp-policy-16.md:21-23,158-187`) | **Fijo `Q1.15`**, `[-1,1-2⁻¹⁵]` (`dsp_common.py:1-10`, `rrc_defs.vh`) |
| Barrido | `W=8,10,12,14,16,18 (+20)`, fases A–E (RNE/trunc, overflow, acc `2W+1/2/3`, FFT A/B, sensibilidad Q1); se elige menor `W` que pase **ambos dominios** (`fxp-policy-16.md:265-274`, `plan-gantt.md:64-69`) | Sin barrido; un solo Q1.15 |
| Redondeo/sat. | RNE en cada angostamiento; saturación solo en salida; acumuladores fallan en overflow; tiempo `2W+3`, FFT base A crece `W…W+4` +4 guardas IFFT, base B 1 bit/etapa (`fxp-policy-16.md:26-43,189-248`) | `round-half-away+clamp` en Python, `round-half-up (acc+2¹⁴)>>>15+sat` en RTL; acc `Q8.30 38b =32+ceil(log2 33)`; peor caso `33·2¹⁵·2¹⁵=2³⁵·⁰⁴` → 37b < 38b **provablemente sin wrap**, asertado cada run (`golden_model.py:81-85`, README bit-growth) |
| Métrica | **SQNR compleja `≥40dB` en ambos dominios** + cero overflow/sat + match serial exacto; float T/F `rtol=1e-10,atol=1e-12` (`adr/0005`, `CONTEXT.md:51-53`, `fxp-policy-16.md:298-320`) | **Bit-exact entero** (`conv+(acc+2¹⁴)>>15+sat`, cross-check escalar/vector 256) + **métricas de enlace**: BER, EVM, SNR, ojo (ver §6) |

## 6. Vectores y verificación

| | Local | Externo |
|---|---|---|
| Vectores | `sim/python/` (golden float `golden_time/freq.py`, `fxp.py`, `sqnr.py`, `gen_vectors.py`) → `sim/vectors/` **solo generado**, `.hex` 32b `{Q,I}` + `.sha256` + `vector_manifest.svh` + hashes; nunca compilados en DUT (`adr/0004`, `vector-manifest-schema.md`, `AGENTS.md:38-51`) | `python/gen_stimulus.py → golden_model.py → data/*.hex + stimulus_meta.vh`; `data/` no trackeado, determinista |
| TB | Familia parametrizada, match **código entero exacto** con sign-extend, índice absoluto/esperado/recibido; `valid_i=1,ready_i=1` + burbujas/stalls + backpressure sin pérdida; `II` medido de `valid&&ready`; lee `DATA_WIDTH/SPC/valid/latency` del manifest (`rtl-streaming-17.md`) | `tb_booth_mult.v` (esquinas, 50k random, latencia, `en=0`) + `tb_rrc_fir_axis.v` (vs `golden_output.hex`, stalls/gaps random, legalidad AXI, `first_valid-first_accept==LATENCY`, X→reset, flush); `run_sim.sh` 6 etapas + corners + canal limpio zero-ISI |
| Interfaz | `valid/ready` simple (no AXI-S), `rst_n` async-assert/sync-deassert 2-flop, bus `{Q,I}`, `FFT_LEN=16,HOP=8,…` (`rtl-streaming-17.md:18-40,154-288`) | **AXI4-Stream con backpressure y `tlast`**, **dos enables** (`sample_en=tvalid&tready`, `pipe_en=tready`) para no duplicar en gaps; `s_ready=m_ready`; `valid/tlast` shift `LATENCY` (`rrc_fir_axis.v:39-60`) |
| Resultados | Aún placeholders (`rrc_stream_placeholder.sv`, vectores pendientes) | Booth 0/81986, filtro 0/16384, 16412 in/out con stalls, latencia 12 medida==parámetro, X limpiada, 237 saturaciones bit-exact, **BER 1.10× teoría (54/8174b @8dB, ±14% 1σ), +5.19dB MF (EVM 73.3→40.3%), ojo abierto** |

## 7. RTL / herramientas / PPA

| | Local | Externo |
|---|---|---|
| Lenguaje | **SystemVerilog** (`rtl/common/rrc_pkg.sv`, `-g2012`) (`rtl-streaming-17.md:257-288`, `adr/0006`) | **Verilog-2001** (`-g2005 -Wall`, `timescale 1ns/1ps`, sin init, X-hasta-reset intencional) |
| Multiplicador | Por definir (serial 1 MAC → PEs sistólicos) | **Booth radix-4 propio 16×16→32, 4 etapas** (S1 múltiplos compartidos, S2 select 8→4, S3 4→2, S4 2→1), `B_WIDTH=16` fijo (`booth_mult_r4.v`) |
| Síntesis | **OpenLane 2 Classic `sky130A/hd` v2.3.10**, DUT-only, SDC/PDN/util 50-60% `200×200µm` iguales, esquinas iguales; evidencia `resolved.json/metrics.json/summary.rpt/max/min/checks/power.rpt` + DRC/LVS (`openlane-env-19.md`, `toolchain-gap-2.md:94-170`) | **Quartus Prime Cyclone V `5CSEMA5F31C6` (DE1-SoC)**, `HIGH PERFORMANCE/SPEED`, retiming ON, **`AUTO_DSP_RECOGNITION OFF`** para medir Booth en fabric; `syn/build.tcl`, `report_timing.tcl` |
| Reloj | **100 MHz primario**, fallback **10 MHz** etiquetado separado, nunca rankeados juntos (`plan-gantt.md:42,89`, `ppa-matrix-18.md:219-230`) | **250 MHz (4ns)**, reloj virtual, 30% I/O, `rst_n` temporizado (`syn/rrc_fir.sdc`) |
| Matriz PPA | **12 filas** (2 serial +6 t +3 f +1 folded), workload 1024/2048/2055, frec 257 bloques, VCD/SAIF por candidato, ranking puertas→Pareto área vs throughput + pot/salida (`ppa-matrix-18.md:21-56,122-134,231-305`) | Sin matriz; tabla a llenar Fmax/ALMs/slack en `syn/output/`; **scripts listos, no corridos** (“scripts written, not run”); `hw_demo/top_single_channel.v` **21-tap 1-canal** porque 33-tap dual (~14k LEs > 6272 EP4CE6) |
| Sim toolchain | Python 3.12 `numpy/scipy/matplotlib/fxpmath/pytest`, Icarus `iverilog+vvp` req., Verilator lint opt., GTKWave manual (`toolchain-gap-2.md:36-77`) | `numpy/scipy/matplotlib` + Icarus 12.0, `DUMP=1` → VCD |

## 8. Gestión / entregables

Local: F0→F5 (`v0.1-float/v0.2-fxp/v0.3-serial/v1.0-opt/v1.1-close`), crítico `T13→T20→T22→T30/T32`, 4-way A-Tiempo/Ignacio, B-Frec/Juan, C-Sim+FXP/Matías (guardián vectores), D-PPA+close/Andrés, cross-review A↔B,C↔D (`plan-gantt.md:7-40,105-122`). Cierre con **contraste T-vs-F + PPA + lecciones + Gantt real vs plan en `docs/slides/*.pdf`** (`CONTEXT.md:112-114`).
Externo: individual, sin Gantt; entrega es **README 8.6kB + `docs/*.png` (constelación, taps, ojo/ojo-limpio)** + scripts Tcl/SDC reutilizables.

## 9. Qué tomar prestado (y qué no)

**Recomendado importar:**
1. Pre-cómputo S1 `±A,±2A` de Booth y ROM en `case` para constant-folding (con nota de costo RAM vs folding).
2. Patrón dos-enables AXI / equivalente `valid/ready` anti-doble-transferencia + test stalls/gaps con conteo in==out.
3. Aserción `medido==parámetro` de latencia y prueba X-tras-reset.
4. Batería corners (rieles, swing máximo, impulsos, ±1LSB) + canal limpio zero-ISI con ojo.
5. `analyze_results.py`-like: aunque el DoD local es SQNR+matching, un anexo BER/EVM/ojo daría el argumento “es el filtro correcto, no solo bit-exact”.
6. Documentar `syn/*` + `hw_demo` aunque no se corra, como hace el externo (“scripts written, not run”).

**No importar sin adaptar:**
- α=0.35, sps=4, 33 taps, Q1.15, Gray/√2, AWGN — violan contratos 13/15/16 locales.
- AXI-S completo y Verilog-2001 — el local exige SV + `valid/ready` simple + `rrc_pkg.sv`.
- Solo-tiempo / solo-unfolded — perdería el contraste tiempo-vs-frecuencia y serial→opt que se califica.
- Ranking por BER sola — el local exige puertas de matching/signoff/timing y Pareto sin pesos.

## 10. Tabla resumen 1-página

| Eje | Local | Externo | Veredicto |
|---|---|---|---|
| Filtro | 8 taps, α0.5, 2× | 33 taps, α0.35, 4× | Distinta consigna; el corto favorece PPA/FFT16 |
| Dominios | Tiempo **y** frecuencia OLS-50% | Solo tiempo | Local más amplio pedagógicamente |
| Paralelismo | Serial II=8 → S/U/P/F | Unfolded ×33 directo | Externo = punto de llegada de una fila local |
| FXP | Barrido W común, SQNR≥40dB | Q1.15 único probado | Local más riguroso en metodología; externo más probado en enlace |
| Verificación | Matching exacto + manifest | Bit-exact + BER/EVM/ojo | Complementarios; conviene anexar BER local |
| Interfaz | valid/ready | AXI-S 2-enables | Idea de 2-enables reutilizable |
| Síntesis | OpenLane sky130 100/10MHz | Quartus CycloneV 250MHz (no corrido) | Distinto flujo; ambos honestos al no inventar números |
| Equipo | 4 + Gantt + slides | Individual + README | Local evalúa proceso; externo evalúa producto |

## Anexo A — Escala de energía: ¿Es=2 (±1±j) o Es=1 (±1±j/√2)?

No es una decisión física, es de **convención de análisis vs. representación en hardware**:

- **Análisis / enlace (link budget, BER, EVM):** la convención es **energía media unitaria `Es=1`**. `BER_QPSK = Q(sqrt(Es/N0))` con `N0=σ²` directo; por eso el externo divide por `√2` (`gen_stimulus.py:88-89`) y las herramientas SDR (GNU Radio, MATLAB) asumen potencia unitaria.
- **Hardware fijo:** la escala real la fija el **rango del formato + headroom**, no la convención. El externo usa `Q1.15` (`[-1,1)`), donde `±1±j` no entra (necesitaría `±1.414`); por eso **tuvo que** normalizar a `±0.707±0.707j` y luego aplicar `headroom 0.92` para el sobrepico del RRC.
- **Local:** el formato `Q2.(W-2)` con rango `[-2,+2)` fue elegido para que `±1±j` entre **exacto** (`+1/-1` son representables sin error), y los coeficientes se normalizan a energía unitaria `sum(h²)=1`. Con `Es=2` el SQNR no se degrada porque el error de cuantización del input es **cero** para símbolos; el factor `√2` de ganancia es irrelevante para un filtro lineal.

**Producción:** mantiene las dos cosas separadas — (1) análisis y presupuesto de enlace en `Es=1`; (2) la escala del punto fijo se elige por **rango del formato, representabilidad exacta y headroom para el PAPR del pulso** (RRC QPSK tiene PAPR ~3.5 dB, ver [ITU/Kaleidoscope 2016](https://www.itu.int/en/ITU-T/academia/kaleidoscope/2016/Documents/S3.3%20Sharafat%20PAPR%20Presentation.pdf)), con AGC absorbiendo la ganancia. Recortar (clip) es lo que arruina BER, por eso el backoff.

**Recomendación local:** **no cambiar** RTL ni vectores (`Es=2`, `Q2.(W-2)`). Si se anexa BER/EVM (punto P5), aplicar `1/√2` **solo en el script de análisis**, como hace el externo, y documentar en el contrato 15/16 que la escala es convención de link budget. Cambiar a `Es=1` en el RTL solo agregaría error de cuantización al input sin beneficio.

## Anexo B — Taps recargables y "folding" (desambiguación)

Dos "folding" distintos que conviene no confundir:

1. **Constant folding** (optimización de síntesis): si el coeficiente es una **constante de compilación**, el sintetizador propaga el valor, colapsa los muxes del recoder de Booth y convierte cada multiplicador en una **red fija de shifts + sumas** (Constant Coefficient Multiplier, KCM). Referencias: [Kastner et al., FPGA FIR add-and-shift](https://cseweb.ucsd.edu/~kastner/papers/tech-fir_add_shift.pdf), [Garcia/Volkova MCM](https://arxiv.org/pdf/2210.02742). Mucho menor área/potencia que un multiplicador 16×16 genérico.
2. **Folding arquitectural** (del proyecto local): reutilizar **un operador en el tiempo** (`F=2`, `S` PEs) para ahorrar área a costa de throughput. No tiene nada que ver con el anterior.

**Taps recargables** = coeficientes en **RAM/registros escribibles** en runtime (no constantes). Se usan cuando el pulso cambia en campo: radio multi-estándar (distinto roll-off), matched filter a un pulso desconocido, ecualizador adaptativo, o reconfiguración sin resintetizar.

**Por qué se pierde el constant folding:** si `b` (el coeficiente) sale de una RAM, es una **variable**, no una constante; el sintetizador debe conservar el recoder de Booth completo, los 8 muxes de selección `{0,±A,±2A}` y el multiplicador general. Sube área/potencia y agrega lectura de memoria al camino.

**Trade-off para el proyecto local:** los 8 taps están **fijados por la consigna** (α=0.5), así que hardwiring es estrictamente mejor: usen la ROM en `case` para habilitar el folding y dejen `$readmemh` solo para sim (como el externo, que testea ambas para que ninguna ruta se rompa). La variante "recargable" no aporta nada al ejercicio; si se quisiera justificar en slides, es una fila de contraste área vs. flexibilidad, no una fila del PPA principal. **Ojo:** `rtl/common/rrc_pkg.sv` congela la tabla de coeficientes (contrato 17 D8), lo cual es coherente con hardwiring.
