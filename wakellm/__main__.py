import argparse
import sys
import time

from .orchestrator import WakeLLM


def main():
    parser = argparse.ArgumentParser(description="WakeLLM Orchestrator")
    parser.add_argument("action", choices=["start", "stop", "status"], help="Action to perform")
    args = parser.parse_args()

    engine = WakeLLM()

    if args.action == "start":
        # Start the API server first so /wake is reachable even during pod boot.
        engine.start_api_server()

        try:
            engine.start_lifecycle()

            # Keep the main thread alive until a monitor triggers shutdown or user interrupts.
            while engine.get_state() not in (engine.STATE_STOPPED, engine.STATE_STOPPING):
                time.sleep(1)

        except KeyboardInterrupt:
            engine.shutdown()

    elif args.action == "stop":
        engine.stop_pod()

    elif args.action == "status":
        pod_info = engine.get_pod_info()
        if pod_info:
            print(f"Pod {pod_info['id']}: desiredStatus={pod_info['desiredStatus']}, "
                  f"runtime={'active' if pod_info.get('runtime') else 'none'}")
        else:
            print("[ERROR] Could not retrieve pod info.")


if __name__ == "__main__":
    main()
