from typing import List

from fastapi import APIRouter, Request, BackgroundTasks, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app import schemas
from app.chain.subscribe import SubscribeChain
from app.core.config import settings
from app.db import get_db
from app.db.models.subscribe import Subscribe
from app.db.models.user import User
from app.db.userauth import get_current_active_superuser
from app.utils.types import MediaType

router = APIRouter()


def start_subscribe_chain(title: str,
                          mtype: MediaType, tmdbid: str, season: int, username: str):
    """
    启动订阅链式任务
    """
    SubscribeChain().process(title=title,
                             mtype=mtype, tmdbid=tmdbid, season=season, username=username)


@router.get("/", response_model=List[schemas.Subscribe])
async def read_subscribes(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_superuser)):
    """
    查询所有订阅
    """
    if not current_user:
        raise HTTPException(
            status_code=400,
            detail="需要授权",
        )
    return Subscribe.list(db)


@router.post("/seerr", response_model=schemas.Response)
async def seerr_subscribe(request: Request, background_tasks: BackgroundTasks,
                          authorization: str = Header(None)):
    """
    Jellyseerr/Overseerr订阅
    """
    if not authorization or authorization != settings.API_TOKEN:
        raise HTTPException(
            status_code=400,
            detail="授权失败",
        )
    req_json = await request.json()
    if not req_json:
        raise HTTPException(
            status_code=500,
            detail="报文内容为空",
        )
    notification_type = req_json.get("notification_type")
    if notification_type not in ["MEDIA_APPROVED", "MEDIA_AUTO_APPROVED"]:
        return {"success": False, "message": "不支持的通知类型"}
    subject = req_json.get("subject")
    media_type = MediaType.MOVIE if req_json.get("media", {}).get("media_type") == "movie" else MediaType.TV
    tmdbId = req_json.get("media", {}).get("tmdbId")
    if not media_type or not tmdbId or not subject:
        return {"success": False, "message": "请求参数不正确"}
    user_name = req_json.get("request", {}).get("requestedBy_username")
    # 添加订阅
    if media_type == MediaType.MOVIE:
        background_tasks.add_task(start_subscribe_chain,
                                  mtype=media_type,
                                  tmdbid=tmdbId,
                                  title=subject,
                                  season=0,
                                  username=user_name)
    else:
        seasons = []
        for extra in req_json.get("extra", []):
            if extra.get("name") == "Requested Seasons":
                seasons = [int(str(sea).strip()) for sea in extra.get("value").split(", ") if str(sea).isdigit()]
                break
        for season in seasons:
            background_tasks.add_task(start_subscribe_chain,
                                      mtype=media_type,
                                      tmdbid=tmdbId,
                                      title=subject,
                                      season=season,
                                      username=user_name)

    return {"success": True}


@router.get("/refresh", response_model=schemas.Response)
async def refresh_subscribes(
        current_user: User = Depends(get_current_active_superuser)):
    """
    刷新所有订阅
    """
    if not current_user:
        raise HTTPException(
            status_code=400,
            detail="需要授权",
        )
    SubscribeChain().refresh()
    return {"success": True}


@router.get("/search", response_model=schemas.Response)
async def search_subscribes(
        current_user: User = Depends(get_current_active_superuser)):
    """
    搜索所有订阅
    """
    if not current_user:
        raise HTTPException(
            status_code=400,
            detail="需要授权",
        )
    SubscribeChain().search(state='R')
    return {"success": True}
