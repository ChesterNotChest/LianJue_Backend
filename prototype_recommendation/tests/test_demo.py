import sys
sys.path.append('..')

from run_demo import main as run_main


def test_run_demo():
    # smoke test: run main to ensure no uncaught exceptions
    run_main()
