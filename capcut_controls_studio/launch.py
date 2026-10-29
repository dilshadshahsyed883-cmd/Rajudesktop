import sys
if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test-report':
        from capcut_controls_studio.smoke import run
        raise SystemExit(run(sys.argv[2]))
    from capcut_controls_studio.app import main
    raise SystemExit(main())
