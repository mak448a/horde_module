import asyncio
from io import BytesIO
import base64
import os
import requests
import yaml
from PIL import Image
from requests.exceptions import ConnectionError
import logging

"""Modified by mak448a on 6/4/23. Changed the request cli to be a module. Added Async to module

Note: don't expect clean code"""


class RequestData(object):
    def __init__(self):
        self.client_agent = "cli_request_dream.py:1.1.0:(discord)db0#1625"
        self.api_key = "0000000000"
        self.filename = "horde_dream.png"
        self.imgen_params = {
            "n": 10,
            "width": 64 * 8,
            "height": 64 * 8,
            "steps": 20,
            "sampler_name": "k_euler_a",
            "cfg_scale": 7.5,
            "denoising_strength": 0.6,
        }
        self.submit_dict = {
            "prompt": "a horde of cute stable robots in a sprawling server room repairing a massive mainframe",
            "nsfw": False,
            "censor_nsfw": False,
            "trusted_workers": False,
            "models": ["stable_diffusion"],
            "r2": True,
            "dry_run": False
        }
        self.source_image = None
        self.source_processing = "img2img"
        self.source_mask = None

    def get_submit_dict(self):
        submit_dict = self.submit_dict.copy()
        submit_dict["params"] = self.imgen_params
        submit_dict["source_processing"] = self.source_processing
        if self.source_image:
            final_src_img = Image.open(self.source_image)
            buffer = BytesIO()
            # We send as WebP to avoid using all the horde bandwidth
            final_src_img.save(buffer, format="Webp", quality=95, exact=True)
            submit_dict["source_image"] = base64.b64encode(buffer.getvalue()).decode("utf8")
        if self.source_mask:
            final_src_mask = Image.open(self.source_mask)
            buffer = BytesIO()
            # We send as WebP to avoid using all the horde bandwidth
            final_src_mask.save(buffer, format="Webp", quality=95, exact=True)
            submit_dict["source_mask"] = base64.b64encode(buffer.getvalue()).decode("utf8")
        return (submit_dict)


class Generator:
    def __init__(self):
        self.api_key = None
        self.prompt = None
        self.filename = None
        self.amount = None
        self.model = None

    def load_request_data(self):
        request_data = RequestData()
        if os.path.exists("cliRequestsData_Dream.yml"):
            with open("cliRequestsData_Dream.yml", "rt", encoding="utf-8", errors="ignore") as configfile:
                config = yaml.safe_load(configfile)
                for key, value in config.items():
                    setattr(request_data, key, value)
        if self.api_key: request_data.api_key = self.api_key
        if self.filename: request_data.filename = self.filename
        if self.amount: request_data.imgen_params["n"] = self.amount
        # if self.width: request_data.imgen_params["width"] = self.width
        # if self.height: request_data.imgen_params["height"] = self.height
        # if self.steps: request_data.imgen_params["steps"] = self.steps
        if self.prompt: request_data.submit_dict["prompt"] = self.prompt
        if self.model: request_data.submit_dict["model"] = self.model
        # if self.nsfw: request_data.submit_dict["nsfw"] = self.nsfw
        # if self.censor_nsfw: request_data.submit_dict["censor_nsfw"] = self.censor_nsfw
        # if self.trusted_workers: request_data.submit_dict["trusted_workers"] = self.trusted_workers
        # if self.source_image: request_data.source_image = self.source_image
        # if self.source_processing: request_data.source_processing = self.source_processing
        # if self.source_mask: request_data.source_mask = self.source_mask
        # if self.dry_run: request_data.submit_dict["dry_run"] = self.dry_run
        return request_data

    async def generate(self, prompt: str, api_key: str, filename: str, amount: int, model: str):
        self.prompt = prompt
        self.api_key = api_key
        self.filename = filename
        self.amount = amount
        self.model = model

        request_data = self.load_request_data()
        # final_submit_dict["source_image"] = 'Test'
        headers = {
            "apikey": request_data.api_key,
            "Client-Agent": request_data.client_agent,
        }
        submit_req = requests.post(f'https://stablehorde.net/api/v2/generate/async', json=request_data.get_submit_dict(),
                                   headers=headers)
        if submit_req.ok:
            submit_results = submit_req.json()
            req_id = submit_results.get('id')
            if not req_id:
                return
            is_done = False
            retry = 0
            cancelled = False
            try:
                while not is_done:
                    try:
                        chk_req = requests.get(f'https://stablehorde.net/api/v2/generate/check/{req_id}')
                        if not chk_req.ok:
                            return
                        chk_results = chk_req.json()
                        print(f"Wait time: {chk_results['wait_time']}    Queue position: "
                              f"{chk_results['queue_position']}    Prompt: {prompt}")
                        is_done = chk_results['done']
                        await asyncio.sleep(0.8)
                    except ConnectionError as e:
                        retry += 1
                        if retry < 10:
                            await asyncio.sleep(1)
                            continue
                        raise
            except KeyboardInterrupt:
                cancelled = True
                retrieve_req = requests.delete(f'https://stablehorde.net/api/v2/generate/status/{req_id}')
            if not cancelled:
                retrieve_req = requests.get(f'https://stablehorde.net/api/v2/generate/status/{req_id}')
            if not retrieve_req.ok:
                return
            results_json = retrieve_req.json()
            if results_json['faulted']:
                final_submit_dict = request_data.get_submit_dict()
                if "source_image" in final_submit_dict:
                    final_submit_dict[
                        "source_image"] = f"img2img request with size: {len(final_submit_dict['source_image'])}"
                return
            results = results_json['generations']
            for iter in range(len(results)):
                final_filename = request_data.filename
                if len(results) > 1:
                    final_filename = f"{iter}_{request_data.filename}"
                if request_data.get_submit_dict()["r2"]:
                    try:
                        img_data = requests.get(results[iter]["img"]).content
                    except:  # NOQA
                        pass
                    with open(final_filename, 'wb') as handler:
                        handler.write(img_data)
                else:
                    b64img = results[iter]["img"]
                    base64_bytes = b64img.encode('utf-8')
                    img_bytes = base64.b64decode(base64_bytes)
                    img = Image.open(BytesIO(img_bytes))
                    img.save(final_filename)
        else:
            pass
