from brotato_bot import cli


def test_dataset_build_command_registered():
    args = cli.build_parser().parse_args(["dataset", "build", "--pck", "x.pck", "--out", "o.json"])
    assert args.pck == "x.pck"
    assert args.out == "o.json"
    assert callable(args.func)
