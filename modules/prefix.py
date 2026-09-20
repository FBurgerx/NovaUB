import json
import os
from telethon.tl.custom import Message

async def prefix_cmd(client, message, args):
    path = f"config-{client._self_id}.json"
    cfg = {"prefix": "."}
    if os.path.exists(path):
        with open(path, "r") as f:
            try: 
                cfg = json.load(f)
            except: 
                pass

    if not args:
        current = cfg.get("prefix", ".")
        return await message.edit(f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Settings</b>\n<blockquote><b>Current prefix:</b> <code>{current}</code></blockquote>", parse_mode='html')

    new_prefix = args[0][:3]
    cfg["prefix"] = new_prefix
    with open(path, "w") as f: 
        json.dump(cfg, f, indent=4)
    client.prefix = new_prefix
    await message.edit(f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Settings</b>\n<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <b>Prefix set to:</b> <code>{new_prefix}</code></blockquote>", parse_mode='html')

def register(app, commands, module_name):
    commands["prefix"] = {"func": prefix_cmd, "module": module_name}