import sys

if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-test-report':
        from t_builder.release_smoke import run
        raise SystemExit(run(sys.argv[2]))
    from t_builder.ui import main
    raise SystemExit(main())
