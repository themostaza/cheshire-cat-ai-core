import traceback
import asyncio

from fastapi import APIRouter, WebSocketDisconnect, WebSocket
from fastapi.concurrency import run_in_threadpool
from fastapi import WebSocketException, status

from cat.looking_glass.cheshire_cat import StrayCat
from cat.log import log

router = APIRouter()

async def receive_message(websoket: WebSocket, stray: StrayCat):
    """
    Continuously receive messages from the WebSocket and forward them to the `ccat` object for processing.
    """

    while True:
        # Receive the next message from the WebSocket.
        user_message = await websoket.receive_json()
        user_message["user_id"] = stray.user_id

        # Run the `ccat` object's method in a threadpool since it might be a CPU-bound operation.
        cat_message = await run_in_threadpool(stray, user_message)

        # Send the response message back to the user.
        await websoket.send_json(cat_message)


async def check_messages(websoket: WebSocket, stray: StrayCat):
    """
    Periodically check if there are any new notifications from the `ccat` instance and send them to the user.
    """

    while True:
        # extract from FIFO list websocket notification
        notification = await stray.ws_messages.get()
        await websoket.send_json(notification)


@router.websocket("/ws")
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str = "user"):
    """
    Endpoint to handle incoming WebSocket connections by user id, process messages, and check for messages.
    """

    # Retrieve the `ccat` instance from the application's state.
    ccat = websocket.app.state.ccat
    strays = websocket.app.state.strays

    # Skip the coroutine if the same user is already connected via WebSocket.
    if user_id in strays.keys():
        stray = strays[user_id]
        stray._ws.close()
        stray._ws = websocket
        #log.error(f"A websocket connection with ID '{user_id}' has already been opened.")
        
        # raise WebSocketException(
        #     code=status.WS_1008_POLICY_VIOLATION, 
        #     reason=f"A websocket connection with ID '{user_id}' has already been opened."
        # )
    else:
        # Temporary conversation-based `cat` object as seen from hooks and tools.
        # Contains working_memory and utility pointers to main framework modules
        # It is passed to both memory recall and agent to read/write working memory
        stray = StrayCat(
            user_id=user_id,
            _llm=ccat._llm,
            embedder=ccat.embedder,
            memory=ccat.memory,
            agent_manager=ccat.agent_manager,
            mad_hatter=ccat.mad_hatter,
            rabbit_hole=ccat.rabbit_hole,
            ws=websocket
        )
        strays[user_id] = stray

    # Add the new WebSocket connection to the manager.
    await websocket.accept()
    try:
        # Process messages and check for notifications concurrently.
        await asyncio.gather(
            receive_message(websocket, stray),
            check_messages(websocket, stray)
        )
    except WebSocketDisconnect:
        # Handle the event where the user disconnects their WebSocket.
        log.info("WebSocket connection closed")
    except Exception as e:
        # Log any unexpected errors and send an error message back to the user.
        log.error(e)
        traceback.print_exc()
        await websocket.send_json({
            "type": "error",
            "name": type(e).__name__,
            "description": str(e)
        })
    # finally:
    #     del strays[user_id]
        # Remove the WebSocket from the manager when the user disconnects.
        #websocket.close()
