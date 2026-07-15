#!/usr/bin/env bash
set -u

INTERVAL=5
CPU_WARN=85
CPU_DANGER=95
GPU_WARN=75
GPU_DANGER=83
NVME_WARN=65
NVME_DANGER=75
NVME_SENSOR_WARN=85
NVME_SENSOR_DANGER=95
LOG_FILE="logs/hardware-guard.log"
KILL_ON_DANGER=0
PID_TO_KILL=""

usage() {
  printf '%s\n' "Usage: $0 [--interval seconds] [--pid PID] [--kill-on-danger]"
  printf '%s\n' ""
  printf '%s\n' "Monitors CPU, GPU, and NVMe temperatures. Sends desktop notifications on warnings."
  printf '%s\n' "Defaults: CPU ${CPU_WARN}/${CPU_DANGER}C, GPU ${GPU_WARN}/${GPU_DANGER}C, NVMe composite ${NVME_WARN}/${NVME_DANGER}C."
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --interval)
      INTERVAL="${2:-}"
      shift 2
      ;;
    --pid)
      PID_TO_KILL="${2:-}"
      shift 2
      ;;
    --kill-on-danger)
      KILL_ON_DANGER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v sensors >/dev/null 2>&1; then
  printf 'Missing required command: sensors\n' >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"

notify() {
  level="$1"
  title="$2"
  body="$3"

  printf '%s [%s] %s - %s\n' "$(date '+%F %T')" "$level" "$title" "$body" >> "$LOG_FILE"

  if command -v notify-send >/dev/null 2>&1; then
    urgency="normal"
    [ "$level" = "DANGER" ] && urgency="critical"
    notify-send -u "$urgency" "$title" "$body" >/dev/null 2>&1 || true
  fi
}

max_cpu_temp() {
  sensors | awk '
    /Package id 0:|Core [0-9]+:/ {
      if (match($0, /\+[0-9]+(\.[0-9]+)?°C/)) {
        temp = substr($0, RSTART + 1, RLENGTH - 3) + 0
        if (temp > max) max = temp
      }
    }
    END { if (max != "") printf "%.0f", max }
  '
}

max_nvme_composite_temp() {
  sensors | awk '
    /^nvme-/ { in_nvme = 1; next }
    /^[^[:space:]].*Adapter:/ { next }
    /^[^[:space:]][^:]*$/ && $0 !~ /^nvme-/ { in_nvme = 0 }
    in_nvme && /Composite:/ {
      if (match($0, /\+[0-9]+(\.[0-9]+)?°C/)) {
        temp = substr($0, RSTART + 1, RLENGTH - 3) + 0
        if (temp > max) max = temp
      }
    }
    END { if (max != "") printf "%.0f", max }
  '
}

max_nvme_sensor_temp() {
  sensors | awk '
    /^nvme-/ { in_nvme = 1; next }
    /^[^[:space:]].*Adapter:/ { next }
    /^[^[:space:]][^:]*$/ && $0 !~ /^nvme-/ { in_nvme = 0 }
    in_nvme && /Sensor [0-9]+:/ {
      if (match($0, /\+[0-9]+(\.[0-9]+)?°C/)) {
        temp = substr($0, RSTART + 1, RLENGTH - 3) + 0
        if (temp > max) max = temp
      }
    }
    END { if (max != "") printf "%.0f", max }
  '
}

gpu_temp() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | awk 'NR == 1 { printf "%.0f", $1 + 0 }'
  fi
}

model_process_status() {
  if [ -n "$PID_TO_KILL" ] && kill -0 "$PID_TO_KILL" >/dev/null 2>&1; then
    printf 'pid %s alive' "$PID_TO_KILL"
  elif [ -n "$PID_TO_KILL" ]; then
    printf 'pid %s not running' "$PID_TO_KILL"
  else
    printf 'no pid configured'
  fi
}

maybe_kill_model() {
  reason="$1"
  if [ "$KILL_ON_DANGER" -eq 1 ] && [ -n "$PID_TO_KILL" ] && kill -0 "$PID_TO_KILL" >/dev/null 2>&1; then
    notify "DANGER" "Hardware Guard: stopping model" "$reason; sending TERM to PID $PID_TO_KILL"
    kill -TERM "$PID_TO_KILL" >/dev/null 2>&1 || true
  fi
}

last_cpu_state="OK"
last_gpu_state="OK"
last_nvme_state="OK"
last_nvme_sensor_state="OK"

printf 'Hardware guard started. Log: %s\n' "$LOG_FILE"
printf 'Thresholds: CPU %s/%sC, GPU %s/%sC, NVMe composite %s/%sC, NVMe sensor %s/%sC\n' "$CPU_WARN" "$CPU_DANGER" "$GPU_WARN" "$GPU_DANGER" "$NVME_WARN" "$NVME_DANGER" "$NVME_SENSOR_WARN" "$NVME_SENSOR_DANGER"
printf 'Press Ctrl+C to stop.\n'

while true; do
  now="$(date '+%F %T')"
  cpu="$(max_cpu_temp)"
  gpu="$(gpu_temp)"
  nvme="$(max_nvme_composite_temp)"
  nvme_sensor="$(max_nvme_sensor_temp)"
  proc="$(model_process_status)"

  cpu_display="n/a"
  gpu_display="n/a"
  nvme_display="n/a"
  nvme_sensor_display="n/a"
  [ -n "$cpu" ] && cpu_display="${cpu}C"
  [ -n "$gpu" ] && gpu_display="${gpu}C"
  [ -n "$nvme" ] && nvme_display="${nvme}C"
  [ -n "$nvme_sensor" ] && nvme_sensor_display="${nvme_sensor}C"

  line="$now CPU=$cpu_display GPU=$gpu_display NVMeComposite=$nvme_display NVMeSensorMax=$nvme_sensor_display model=$proc"
  printf '%s\n' "$line"
  printf '%s\n' "$line" >> "$LOG_FILE"

  if [ -n "$cpu" ] && [ "$cpu" -ge "$CPU_DANGER" ]; then
    [ "$last_cpu_state" != "DANGER" ] && notify "DANGER" "CPU temperature critical" "CPU reached ${cpu}C. Stop the model or reduce threads."
    last_cpu_state="DANGER"
    maybe_kill_model "CPU reached ${cpu}C"
  elif [ -n "$cpu" ] && [ "$cpu" -ge "$CPU_WARN" ]; then
    [ "$last_cpu_state" = "OK" ] && notify "WARN" "CPU temperature high" "CPU reached ${cpu}C. Consider fewer llama.cpp threads."
    last_cpu_state="WARN"
  else
    last_cpu_state="OK"
  fi

  if [ -n "$gpu" ] && [ "$gpu" -ge "$GPU_DANGER" ]; then
    [ "$last_gpu_state" != "DANGER" ] && notify "DANGER" "GPU temperature critical" "GPU reached ${gpu}C. Stop the model or reduce GPU load."
    last_gpu_state="DANGER"
    maybe_kill_model "GPU reached ${gpu}C"
  elif [ -n "$gpu" ] && [ "$gpu" -ge "$GPU_WARN" ]; then
    [ "$last_gpu_state" = "OK" ] && notify "WARN" "GPU temperature high" "GPU reached ${gpu}C."
    last_gpu_state="WARN"
  else
    last_gpu_state="OK"
  fi

  if [ -n "$nvme" ] && [ "$nvme" -ge "$NVME_DANGER" ]; then
    [ "$last_nvme_state" != "DANGER" ] && notify "DANGER" "NVMe temperature critical" "NVMe composite reached ${nvme}C. Reduce disk/model load and improve airflow."
    last_nvme_state="DANGER"
    maybe_kill_model "NVMe reached ${nvme}C"
  elif [ -n "$nvme" ] && [ "$nvme" -ge "$NVME_WARN" ]; then
    [ "$last_nvme_state" = "OK" ] && notify "WARN" "NVMe temperature high" "NVMe composite reached ${nvme}C."
    last_nvme_state="WARN"
  else
    last_nvme_state="OK"
  fi

  if [ -n "$nvme_sensor" ] && [ "$nvme_sensor" -ge "$NVME_SENSOR_DANGER" ]; then
    [ "$last_nvme_sensor_state" != "DANGER" ] && notify "DANGER" "NVMe internal sensor critical" "Internal NVMe sensor reached ${nvme_sensor}C. Composite is ${nvme_display}."
    last_nvme_sensor_state="DANGER"
  elif [ -n "$nvme_sensor" ] && [ "$nvme_sensor" -ge "$NVME_SENSOR_WARN" ]; then
    [ "$last_nvme_sensor_state" = "OK" ] && notify "WARN" "NVMe internal sensor high" "Internal NVMe sensor reached ${nvme_sensor}C. Composite is ${nvme_display}."
    last_nvme_sensor_state="WARN"
  else
    last_nvme_sensor_state="OK"
  fi

  sleep "$INTERVAL"
done
