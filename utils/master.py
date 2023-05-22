import os
import sys
import requests
import datetime as dt

from urllib.parse import unquote
from time import sleep

sys.path.append(os.getcwd())
from config.config import ConfigParser

class Master:
    def __init__(self):
        pass
    
    def init(self, configFile):
        self.loadConfig(configFile)
        self.__initSession()
    
    def loadConfig(self, configFile):
        self.configParser = ConfigParser(configFile)
        if not os.path.exists(configFile):
            self.configParser.createConfig()
        self.cfg = self.configParser.parseConfig()
        self.sessionCfg = self.cfg['session']
        self.urls = self.cfg['urls']
        self.planCode = self.cfg["planCode"]
        self.data = self.cfg["data"]
        self.settings = self.cfg["settings"]
        self.userInfo = self.cfg["user_info"]
        self.plans = self.cfg["plans"]
        self.job= self.cfg["job"]
        
        if self.userInfo['login_name'] is None or self.job['maxTrials'] is None:
            self.env2conf()
    
    def env2conf(self):
        env_userid = os.environ.get("HLMUSERID")
        env_password = os.environ.get("HLMPASSWORD")
        env_planCode = os.environ.get("HLMPLANCODE")
        env_max_trials = os.environ.get("HLMMAXTRIALS")
        env_delay = os.environ.get("HLMDELAY")
        if env_userid is not None and env_password is not None and env_planCode is not None:
            self.userInfo["login_name"] = env_userid
            self.userInfo["password"] = env_password
            self.planCode = env_planCode.split(",")
        else:
            print("未设置环境变量，无法自动登录")
            self.configParser.delConfigFile()
            exit(0)
            
        # default job config
        if env_max_trials is None:
            self.job["maxTrials"] = 10  # default max trials
        else:
            self.job["maxTrials"] = int(env_max_trials)
        if env_delay is None or int(env_delay) < 2:
            self.job["delay"] = 2   # default delay
        else:
            self.job["delay"] = int(env_delay)
     
    def delConfigFile(self):
        self.configParser.delConfigFile()
        
    def saveConfig(self):
        self.cfg['planCode'] = self.planCode
        self.cfg['user_info'] = self.userInfo
        self.cfg['plans'] = self.plans
        self.configParser.saveConfig(self.cfg)
    
    def __initSession(self):
        import urllib3
        urllib3.disable_warnings()
        self.session = requests.Session()
        self.session.headers = self.sessionCfg['headers']
        self.session.trust_env = self.sessionCfg['trust_env']
        self.session.verify = self.sessionCfg['verify']
        self.session.params = self.sessionCfg['params']
    
    def login(self):
        url = self.urls["login"]
        loginRes = self.session.post(url=url, data=self.userInfo).json()
        if loginRes["CODE"] == "ok":
            self.uid = loginRes["DATA"]["uid"]
            self.name = loginRes["DATA"]["user_info"]["name"]
        return loginRes["CODE"] == "ok"

    def __queryRooms(self):
        # 查询所有可用的房间类型，返回一个字典，键为房间名，值为房间对应的请求参数
        url = self.urls["query_rooms"]
        queryRoomsRes = self.session.get(url=url).json()
        rawRooms = queryRoomsRes["content"]["children"][1]["defaultItems"]
        rooms = {x["name"]: unquote(x["link"]["url"]).split('?')[1] for x in rawRooms}
        for room in rooms.keys():
            rooms[room] = self.session.get(url=self.urls["query_seats"] + "?" + rooms[room]).json()["data"]
            sleep(1.5) # minimal interval is unknown
        return rooms
    
    def __querySeats(self):
        #  查询每个房间的作为信息
        time = dt.datetime.now()
        if time.hour >= 22:
            time = time + dt.timedelta(days=1)
            time = time.replace(hour=11, minute=0, second=0)
        for room in self.rooms.keys():
            data = {
                "beginTime": time.timestamp(),
                "duration": 3600,
                "num": 1,
                "space_category[category_id]": self.rooms[room]["space_category"]["category_id"],
                "space_category[content_id]": self.rooms[room]["space_category"]["content_id"],
            }
            resp = self.session.post(url=self.urls["query_seats"], data=data).json()
            self.rooms[room]["floors"] = {x["roomName"]:x for x in resp["allContent"]["children"][2]["children"]["children"]}
            for floor in self.rooms[room]["floors"].keys():
                self.rooms[room]["floors"][floor]["seats"] = self.rooms[room]["floors"][floor]["seatMap"]["POIs"]
            sleep(2)
    def updateRooms(self):
        self.rooms = self.__queryRooms()
        self.__querySeats()
        return list(self.rooms.keys())
    
    def getFloorNamesByRoom(self, roomName):
        floors = self.rooms[roomName]["floors"]
        return list(floors.keys())
    
    def getFloorNameByRoomAndId(self,room,id):
        for floor in self.rooms[room]['floors']:
            thisFloor=self.rooms[room]['floors'][floor]
            if thisFloor['seatMap']['info']['id'] == str(id):
                return floor
        return None
    
    def getSeatsByRoomAndFloor(self, roomName, floorName):
        seats = self.rooms[roomName]["floors"][floorName]["seats"]
        return seats
    
    def getRoomDetails(self):
        details={}
        for room in self.rooms:
            details[room]={}
            for floor in self.rooms[room]['floors']:
                thisFloor=self.rooms[room]['floors'][floor]
                details[room][floor]=thisFloor['seatMap']['info']['id']
        return details
    
    def addPlan(self, roomName, beginTime, duration, seatsInfo, seatBookers):
        self.plans.append({
            "roomName": roomName,
            "beginTime": beginTime,
            "duration": duration,
            "seatsInfo": list(seatsInfo),
            "seatBookers": list(seatBookers),
        })
    
    def plan2data(self, plan):
        data = {}
        data["beginTime"] = int(plan["beginTime"].timestamp())
        data["duration"] = plan["duration"]*3600
        for i in range(len(plan["seatsInfo"])):
            data[f"seats[{i}]"] = plan["seatsInfo"][i]["seatId"]
            data[f"seatBookers[{i}]"] = plan["seatBookers"][i]
        return data
    
    def run(self, plan):
            data = self.plan2data(plan)
            url = self.urls["book_seat"]
            res = self.session.post(url=url, data=data).json()
            return res

if __name__ == "__main__":
    pass
