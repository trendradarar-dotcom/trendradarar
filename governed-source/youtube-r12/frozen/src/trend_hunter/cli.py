from __future__ import annotations

import argparse
import json

from .api import create_app
from .bootstrap import bootstrap_governance
from .db import init_db
from .ledger import GovernanceLedger
from .pipeline import SyntheticPilotRunner


def main() -> None:
    parser = argparse.ArgumentParser(prog="trend-hunter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def dbarg(p):
        p.add_argument("--db", default="data/trend_hunter.db")

    p=sub.add_parser("init-db"); dbarg(p)
    p=sub.add_parser("bootstrap-governance"); dbarg(p)
    p=sub.add_parser("demo"); dbarg(p)
    p=sub.add_parser("audit"); dbarg(p)
    p=sub.add_parser("serve"); dbarg(p); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8000); p.add_argument("--auth-required",action="store_true")
    p=sub.add_parser("ingest-json"); dbarg(p); p.add_argument("path")
    p=sub.add_parser("export-snapshot"); dbarg(p); p.add_argument("output")
    p=sub.add_parser("ingest-gdelt"); dbarg(p); p.add_argument("query"); p.add_argument("--timespan",default="1h"); p.add_argument("--maxrecords",type=int,default=100)
    p=sub.add_parser("ingest-youtube"); dbarg(p); p.add_argument("query"); p.add_argument("--api-key-env",default="YOUTUBE_API_KEY"); p.add_argument("--region"); p.add_argument("--language"); p.add_argument("--published-after"); p.add_argument("--max-results",type=int,default=25)
    p=sub.add_parser("ingest-google-trends-export"); dbarg(p); p.add_argument("path"); p.add_argument("--region")
    p=sub.add_parser("ingest-tiktok-snapshot"); dbarg(p); p.add_argument("path"); p.add_argument("--region"); p.add_argument("--language")
    p=sub.add_parser("ingest-instagram-snapshot"); dbarg(p); p.add_argument("path"); p.add_argument("--region"); p.add_argument("--language")
    p=sub.add_parser("ingest-snapchat-snapshot"); dbarg(p); p.add_argument("path"); p.add_argument("--region"); p.add_argument("--language")
    p=sub.add_parser("issue-token"); p.add_argument("--subject",required=True); p.add_argument("--roles",required=True,help="comma-separated roles"); p.add_argument("--ttl-seconds",type=int,default=3600); p.add_argument("--secret-env",default="TREND_HUNTER_AUTH_SECRET")
    p=sub.add_parser("register-operator"); dbarg(p); p.add_argument("--subject",required=True); p.add_argument("--display-name"); p.add_argument("--roles",default=""); p.add_argument("--scopes",default="*")
    p=sub.add_parser("revoke-operator"); dbarg(p); p.add_argument("--subject",required=True); p.add_argument("--reason",default="")
    p=sub.add_parser("configure-transport-security"); dbarg(p); p.add_argument("--mode",required=True,choices=["LOOPBACK_ONLY","DIRECT_TLS","TRUSTED_TLS_TERMINATING_REVERSE_PROXY"]); p.add_argument("--endpoint"); p.add_argument("--trusted-proxy-ip", action="append", default=[])
    p=sub.add_parser("bind-account"); dbarg(p); p.add_argument("--provider",required=True); p.add_argument("--account-ref",required=True); p.add_argument("--account-kind",required=True)
    p=sub.add_parser("bind-channel"); dbarg(p); p.add_argument("--account-binding-state-id",required=True); p.add_argument("--platform",required=True); p.add_argument("--channel-ref",required=True); p.add_argument("--language"); p.add_argument("--region")
    p=sub.add_parser("operational-preflight"); dbarg(p)
    p=sub.add_parser("connector-smoke"); dbarg(p); p.add_argument("provider",choices=["gdelt","youtube"]); p.add_argument("--query",default="technology"); p.add_argument("--region"); p.add_argument("--language")
    p=sub.add_parser("backup"); dbarg(p); p.add_argument("output")
    p=sub.add_parser("restore"); p.add_argument("backup_zip"); p.add_argument("destination_dir")

    args=parser.parse_args()
    if args.cmd=="init-db":
        init_db(args.db); print(f"initialized {args.db}")
    elif args.cmd=="bootstrap-governance":
        init_db(args.db); ledger=GovernanceLedger(args.db); ids=bootstrap_governance(ledger); print(json.dumps(ids,ensure_ascii=False,indent=2))
    elif args.cmd=="demo":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger); r=SyntheticPilotRunner(ledger).run(); print(json.dumps(r.__dict__,ensure_ascii=False,indent=2))
    elif args.cmd=="audit":
        init_db(args.db); ledger=GovernanceLedger(args.db); print(json.dumps(ledger.integrity_check(),ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-gdelt":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.gdelt import GDELTDocConnector
        from .ingest import IngestionService
        c=GDELTDocConnector(args.query,timespan=args.timespan,maxrecords=args.maxrecords)
        refs=IngestionService(ledger).ingest(c.fetch(),c.name); print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-youtube":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.youtube import YouTubeSearchConnector
        from .ingest import IngestionService
        from .security import SecretResolver
        key=SecretResolver.resolve(f"env://{args.api_key_env}")
        c=YouTubeSearchConnector(key,args.query,region_code=args.region,relevance_language=args.language,published_after=args.published_after,max_results=args.max_results)
        refs=IngestionService(ledger).ingest(c.fetch(),c.name); print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-google-trends-export":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.google_trends_export import GoogleTrendsExportConnector
        from .ingest import IngestionService
        c=GoogleTrendsExportConnector(args.path,region=args.region)
        refs=IngestionService(ledger).ingest(c.fetch(),c.name); print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-tiktok-snapshot":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.tiktok_creative_center_snapshot import TikTokCreativeCenterSnapshotConnector
        from .ingest import IngestionService
        c=TikTokCreativeCenterSnapshotConnector(args.path,region=args.region,language=args.language)
        refs=IngestionService(ledger).ingest(c.fetch(),c.name)
        print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-instagram-snapshot":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.instagram_surface_snapshot import InstagramSurfaceSnapshotConnector
        from .ingest import IngestionService
        c=InstagramSurfaceSnapshotConnector(args.path,region=args.region,language=args.language)
        refs=IngestionService(ledger).ingest(c.fetch(),c.name)
        print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-snapchat-snapshot":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.snapchat_spotlight_snapshot import SnapchatSpotlightSnapshotConnector
        from .ingest import IngestionService
        c=SnapchatSpotlightSnapshotConnector(args.path,region=args.region,language=args.language)
        refs=IngestionService(ledger).ingest(c.fetch(),c.name)
        print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="export-snapshot":
        init_db(args.db)
        from .export import export_snapshot
        print(json.dumps(export_snapshot(args.db,args.output),ensure_ascii=False,indent=2))
    elif args.cmd=="ingest-json":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .connectors.manual import ManualJSONConnector
        from .ingest import IngestionService
        c=ManualJSONConnector(args.path); refs=IngestionService(ledger).ingest(c.fetch(),c.name)
        print(json.dumps([r.__dict__ for r in refs],ensure_ascii=False,indent=2))
    elif args.cmd=="issue-token":
        from .security import HMACTokenAuthority
        auth=HMACTokenAuthority.from_env(args.secret_env)
        print(auth.issue(args.subject,[x.strip() for x in args.roles.split(',') if x.strip()],ttl_seconds=args.ttl_seconds))
    elif args.cmd=="register-operator":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .operational import OperationalBindingService
        ref=OperationalBindingService(ledger).register_operator(args.subject,display_name=args.display_name,roles=[x.strip() for x in args.roles.split(',') if x.strip()],scopes=[x.strip() for x in args.scopes.split(',') if x.strip()])
        print(json.dumps(ref.__dict__,ensure_ascii=False,indent=2))
    elif args.cmd=="revoke-operator":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .operational import OperationalBindingService
        ref=OperationalBindingService(ledger).revoke_operator(args.subject,reason=args.reason)
        print(json.dumps(ref.__dict__,ensure_ascii=False,indent=2))
    elif args.cmd=="configure-transport-security":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .operational import OperationalBindingService
        ref=OperationalBindingService(ledger).configure_transport_security(
            args.mode, endpoint=args.endpoint, metadata={"trusted_proxy_ips": args.trusted_proxy_ip} if args.trusted_proxy_ip else None
        )
        print(json.dumps(ref.__dict__,ensure_ascii=False,indent=2))
    elif args.cmd=="bind-account":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .operational import OperationalBindingService
        ref=OperationalBindingService(ledger).bind_external_account(args.provider,args.account_ref,account_kind=args.account_kind)
        print(json.dumps(ref.__dict__,ensure_ascii=False,indent=2))
    elif args.cmd=="bind-channel":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .operational import OperationalBindingService
        ref=OperationalBindingService(ledger).bind_channel(args.account_binding_state_id,args.platform,args.channel_ref,language=args.language,region=args.region)
        print(json.dumps(ref.__dict__,ensure_ascii=False,indent=2))
    elif args.cmd=="connector-smoke":
        from .live import connector_smoke
        from .operational import OperationalBindingService
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        result=connector_smoke(args.provider,query=args.query,region=args.region,language=args.language)
        record=OperationalBindingService(ledger).record_connector_smoke(result)
        result["governed_smoke_state_id"] = record.state_id
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if not result.get("ok"): raise SystemExit(2)
    elif args.cmd=="operational-preflight":
        init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
        from .operational import OperationalPreflight
        print(json.dumps(OperationalPreflight(ledger).report(),ensure_ascii=False,indent=2))
    elif args.cmd=="backup":
        from .backup import create_backup
        print(json.dumps(create_backup(args.db,args.output),ensure_ascii=False,indent=2))
    elif args.cmd=="restore":
        from .backup import restore_backup
        print(json.dumps(restore_backup(args.backup_zip,args.destination_dir),ensure_ascii=False,indent=2))
    elif args.cmd=="serve":
        import os, uvicorn
        non_loopback = args.host not in {"127.0.0.1","localhost","::1"}
        if non_loopback and not args.auth_required:
            raise SystemExit("Refusing non-loopback network exposure without --auth-required")
        if args.auth_required and not os.environ.get("TREND_HUNTER_AUTH_SECRET"):
            raise SystemExit("--auth-required needs TREND_HUNTER_AUTH_SECRET")
        if non_loopback:
            init_db(args.db); ledger=GovernanceLedger(args.db); bootstrap_governance(ledger)
            from .operational import OperationalPreflight
            report=OperationalPreflight(ledger).report()
            if not report.get("ready_for_network_exposure"):
                raise SystemExit("Refusing non-loopback exposure: governed authenticated identity + DIRECT_TLS/TRUSTED_TLS_TERMINATING_REVERSE_PROXY readiness is not satisfied")
        app=create_app(args.db,auth_required=args.auth_required); uvicorn.run(app,host=args.host,port=args.port)

if __name__ == "__main__":
    main()
