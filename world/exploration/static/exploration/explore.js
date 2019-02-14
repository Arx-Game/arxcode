
xDimension = 9;
yDimension = 9;
havenMatrix = null
havenIdNumber = null

gridSizeWidth = 30;
gridSizeHeight = 45;

selectedX = null;
selectedY = null;

canvas = null;
canvas_ctx = null;

baseUri = window.location.protocol + "//" + window.location.host + "/explore/api"

openLineStyle = "#FFB0B0B0";
obstacleLineStyle = "red";

function serialize(obj) {
  var str = [];
  for (var p in obj)
    if (obj.hasOwnProperty(p)) {
      str.push(encodeURIComponent(p) + "=" + encodeURIComponent(obj[p]));
    }
  return str.join("&");
}

function postData(endPoint, body, callbackFunction) {
	var bodyString = serialize(body);
	fetch(baseUri + endPoint, {
		method: 'post',
		body: bodyString,
		headers: {
			"X-CSRFToken": getCookie("csrftoken"),
			"Accept": "application/json",
			"Content-Type": "application/x-www-form-urlencoded"
		}
	})
	.then(function(response) {
			// if (response.status != 200) {
			// 	const reader = response.body.getReader();
			// 	reader.read().then(function process({done, value}) {
			// 		if (done) {
			// 			return;
			// 		}
			// 		stringValue = String.fromCharCode.apply(null, value);
			// 		console.log("Got: " + stringValue);
			// 		return reader.read().then(process);
			// 	});
			// }
			response.json().then(function(data) {
			if (response.status != 200) {
				window.alert(data.error);
			}
			callbackFunction(response.status, data);
		});
	});
}

function getData(endPoint, callbackFunction) {
	fetch(baseUri + endPoint, {
		method: 'get',
		headers: {
			"X-CSRFToken": getCookie("csrftoken"),
			"Accept": "application/json",
		}
	})
	.then(function(response) {
		// if (response.status != 200) {
		// 	const reader = response.body.getReader();
		// 	reader.read().then(function process({done, value}) {
		// 		if (done) {
		// 			return;
		// 		}
		// 		stringValue = String.fromCharCode.apply(null, value);
		// 		console.log("Got: " + stringValue);
		// 		return reader.read().then(process);
		// 	});
		// }
		response.json().then(function(data) {
			if (response.status != 200) {
				window.alert(data.error);
			}
			callbackFunction(response.status, data);
		});
	});
}


function setupCanvas(xDim, yDim, matrix) {
	xDimension = xDim;
	yDimension = yDim;
	havenMatrix = matrix;
	canvas.width = xDimension * gridSizeWidth;
	canvas.height = yDimension * gridSizeHeight;
}

function drawCanvas() {

	canvas_ctx.clearRect(0, 0, canvas.width, canvas.height);

	canvas_ctx.fillStyle = 'black';
	canvas_ctx.beginPath();
	canvas_ctx.moveTo(0,0);
	canvas_ctx.lineTo(canvas.width, 0);
	canvas_ctx.lineTo(canvas.width, canvas.height);
	canvas_ctx.lineTo(0, canvas.height);
	canvas_ctx.lineTo(0, 0);
	canvas_ctx.fill();

	canvas_ctx.strokeColor = "white";

	if (havenMatrix != null) {
		for (var xLoop = 0; xLoop < xDimension; xLoop++) {
			for (var yLoop = 0; yLoop < yDimension; yLoop++) {
				room = havenMatrix[xLoop][yLoop];
				if (room.is_room) {
					var gridX = xLoop * gridSizeWidth;
					var gridY = yLoop * gridSizeHeight;

					canvas_ctx.beginPath();
					canvas_ctx.rect(gridX, gridY, gridSizeWidth, gridSizeHeight);

					if ((xLoop == selectedX) && (yLoop == selectedY)) {
						canvas_ctx.fillStyle = "yellow";
					}
					else {
						canvas_ctx.fillStyle = "white";
					}
					canvas_ctx.fill();

					canvas_ctx.beginPath();
					canvas_ctx.moveTo(gridX, gridY);
					canvas_ctx.lineTo(gridX + gridSizeWidth, gridY)
					canvas_ctx.strokeStyle = room.obstacle_north ? obstacleLineStyle : openLineStyle;
					canvas_ctx.stroke();

					canvas_ctx.beginPath();
					canvas_ctx.moveTo(gridX, gridY + gridSizeHeight);
					canvas_ctx.lineTo(gridX + gridSizeWidth, gridY + gridSizeHeight);
					canvas_ctx.strokeStyle = room.obstacle_south ? obstacleLineStyle : openLineStyle;
					canvas_ctx.stroke();

					canvas_ctx.beginPath();
					canvas_ctx.moveTo(gridX, gridY);
					canvas_ctx.lineTo(gridX, gridY + gridSizeHeight);
					canvas_ctx.strokeStyle = room.obstacle_west ? obstacleLineStyle : openLineStyle;
					canvas_ctx.stroke();

					canvas_ctx.beginPath();
					canvas_ctx.moveTo(gridX + gridSizeWidth, gridY);
					canvas_ctx.lineTo(gridX + gridSizeWidth, gridY + gridSizeHeight);
					canvas_ctx.strokeStyle = room.obstacle_east ? obstacleLineStyle : openLineStyle;
					canvas_ctx.stroke();

					smallGridWidth = (gridSizeWidth - 10) / 2;
					smallGridHeight = (gridSizeHeight - 10) / 2;
					smallDotWidth = gridSizeWidth - (smallGridWidth * 2);
					smallDotHeight = gridSizeHeight - (smallGridHeight * 2);

					if (room.monster) {
						canvas_ctx.fillStyle = "red"
						canvas_ctx.fillRect(gridX + smallGridWidth, gridY + (smallGridHeight - smallDotHeight), smallDotWidth, smallDotHeight);
					}

					if (room.puzzle) {
						canvas_ctx.fillStyle = "green"
						canvas_ctx.fillRect(gridX + smallGridWidth, gridY + gridSizeHeight - smallGridHeight, smallDotWidth, smallDotHeight);
					}

					if (room.entrance) {
						canvas_ctx.fillStyle = "blue";
						canvas_ctx.fillRect(gridX + smallGridWidth, gridY + smallGridHeight, smallDotWidth, smallDotHeight);
					}

				}
			}
		}
	}
}

function getCursorPosition(event) {
    var rect = canvas.getBoundingClientRect();
    var x = event.clientX - rect.left;
    var y = event.clientY - rect.top;
    return [x, y];
}

function setRoomData(data) {
	havenName = document.getElementById("shardhavenName");
	havenDesc = document.getElementById("shardhavenDesc");
	north = document.getElementById("northObstacle");
	south = document.getElementById("southObstacle");
	west = document.getElementById("WestObstacle");
	east = document.getElementById("eastObstacle");
	entranceToggle = document.getElementById("entranceToggle");
	monster = document.getElementById("monster");
	monsterToggle = document.getElementById("monsterDefeated");
	puzzle = document.getElementById("puzzle");
	puzzleToggle = document.getElementById("puzzleSolved");
	saveButton = document.getElementById("shardhavenRoomSave");
	deleteButton = document.getElementById("shardhavenRoomDelete");

	if (data == null) {
		havenName.value = "";
		havenName.disabled = true;
		havenDesc.value = "";
		havenDesc.disabled = true;
		northObstacle.value = "0";
		northObstacle.disabled = true;
		southObstacle.value = "0";
		southObstacle.disabled = true;
		westObstacle.value = "0";
		westObstacle.disabled = true;
		eastObstacle.value = "0";
		eastObstacle.disabled = true;
		saveButton.disabled = true;
		deleteButton.disabled = true;
		entranceToggle.disabled = true;
		entranceToggle.checked = false;
		puzzle.disabled = true;
		puzzle.value = "0";
		puzzleToggle.checked = false;
		puzzleToggle.disabled = true;
		monster.disabled = true;
		monster.value = "0";
		monsterToggle.checked = false;
		monsterToggle.disabled = true;
		return;
	}
	else {
		havenName.value = "";
		havenName.disabled = false;
		havenDesc.value = "";
		havenDesc.disabled = false;
		northObstacle.value = "0";
		southObstacle.value = "0";
		westObstacle.value = "0";
		eastObstacle.value = "0";
		northObstacle.disabled = false;
		southObstacle.disabled = false;
		westObstacle.disabled = false;
		eastObstacle.disabled = false;
		saveButton.disabled = false;
		deleteButton.disabled = false;
		entranceToggle.disabled = false;
		entranceToggle.checked = false;
		puzzle.disabled = false;
		puzzle.value = "0";
		puzzleToggle.checked = false;
		puzzleToggle.disabled = false;
		monster.disabled = false;
		monster.value = "0";
		monsterToggle.checked = false;
		monsterToggle.disabled = false;
	}

	console.log(data);

	if (data['name'] != null) {
		havenName.value = data['name'];
	}

	if (data['description'] != null) {
		havenDesc.value = data['description'];
	}

	if (data['obstacle_north']) {
		northObstacle.value = data['obstacle_north'];
	}

	if (data['obstacle_south']) {
		southObstacle.value = data['obstacle_south'];
	}

	if (data['obstacle_west']) {
		westObstacle.value = data['obstacle_west'];
	}

	if (data['obstacle_east']) {
		eastObstacle.value = data['obstacle_east'];
	}

	if (data['entrance']) {
		entranceToggle.checked = true;
	}

	if (data['monster']) {
		monster.value = data['monster'];
		monsterToggle.checked = data['monster_defeated'];
	}

	if (data['puzzle']) {
		puzzle.value = data['puzzle'];
		puzzleToggle.checked = data['puzzle_solved'];
	}
}

function saveRoom() {
	havenName = document.getElementById("shardhavenName");
	havenDesc = document.getElementById("shardhavenDesc");
	north = document.getElementById("northObstacle");
	south = document.getElementById("southObstacle");
	west = document.getElementById("westObstacle");
	east = document.getElementById("eastObstacle");
	entranceToggle = document.getElementById("entranceToggle");

	result = { 'x': selectedX, 'y': selectedY, 'haven_id': havenIdNumber };
	if (havenName.value.length > 0) {
		result['name'] = havenName.value;
	}
	if (havenDesc.value.length > 0) {
		result['description'] = havenDesc.value;
	}
	if (north.value != "0") {
		result['obstacle_north'] = north.value;
	}
	if (south.value != "0") {
		result['obstacle_south'] = south.value;
	}
	if (west.value != "0") {
		result['obstacle_west'] = west.value;
	}
	if (east.value != "0") {
		result['obstacle_east'] = east.value;
	}
	if (entranceToggle.checked) {
		result['entrance'] = true;
	}
	if (monster.value != "0") {
		result['monster'] = monster.value;
		result['monster_defeated'] = monsterToggle.checked;
	}
	if (puzzle.value != "0") {
		result['puzzle'] = puzzle.value;
		result['puzzle_solved'] = puzzleToggle.checked;
	}

	postData("/haven/room/edit", result, function(status, data) {
		if (status == 200) {
			fetchHaven(havenIdNumber);
		}
	});
}

function deleteRoom() {
	roomData = { 'x': selectedX, 'y': selectedY, 'haven_id': havenIdNumber };
	postData("/haven/room/delete", roomData, function(status, data) {
		if (status == 200) {
			fetchHaven(havenIdNumber);
		}
	});
	selectedX = null;
	selectedY = null;
	setRoomData(null);
}

function editRoom(event) {
	point = getCursorPosition(event);
	var gridX = Math.trunc(point[0] / gridSizeWidth);
	var gridY = Math.trunc(point[1] / gridSizeHeight);

	if ((gridX > 0) && (gridX < xDimension) && (gridY > 0) && (gridY < yDimension)) {
		roomData = havenMatrix[gridX][gridY];
		if (roomData.is_room) {
			selectedX = gridX;
			selectedY = gridY;
			drawCanvas();
			setRoomData(roomData);
		}
		else {
			setRoomData(null);
			data = {
				'haven_id': havenIdNumber,
				'x': gridX,
				'y': gridY
			}
			postData("/haven/room/create", data, function(status, data) {
				if (status == 200) {
					selectedX = gridX;
					selectedY = gridY;
					fetchHaven(havenIdNumber);
				}
			});
		}
	}
}

function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function refreshHavenList() {
	getData("/list", function(status, data) {
		if (status == 200) {
			picker = document.getElementById("shardhavenPicker");
			picker.innerHTML = "";

			pickerOptions = "<option value='0'>----</option>";
			for (var loop = 0; loop < data['havens'].length; loop++) {
				dict = data['havens'][loop];
				pickerOptions += "<option value='" + dict.id + "'>" + dict.name + "</option>"
			}
			picker.innerHTML = pickerOptions;
		}
	});
}

function fetchHaven(havenId) {
	havenIdNumber = null;
	postData("/haven", { 'haven_id': havenId }, function(status, data) {
		if (status == 200) {
			havenIdNumber = havenId;
			if (data.has_layout) {
				setupCanvas(data.x_dim, data.y_dim, data.matrix);
				drawCanvas(data.matrix)
				if ((selectedX != null) && (selectedY != null)) {
					roomData = data.matrix[selectedX][selectedY];
					setRoomData(roomData);
				}
			}
		}
	});
}

function fetchObstacles(havenId) {
	postData("/haven/obstacles", { 'haven_id': havenId }, function(status, data) {
		if (status == 200) {
			var options = "<option value='0'>----</option>"
			for (var loop = 0; loop < data['obstacles'].length; loop++) {
				var dict = data['obstacles'][loop];
				options += "<option value='" + dict.id + "'>" + dict.name + "</option>"
			}

			var picker = document.getElementById("northObstacle");
			picker.innerHTML = options;

			var picker = document.getElementById("southObstacle");
			picker.innerHTML = options;

			var picker = document.getElementById("westObstacle");
			picker.innerHTML = options;

			var picker = document.getElementById("eastObstacle");
			picker.innerHTML = options;
		}
	});
}

function fetchMonsters(havenId) {
	postData("/haven/monsters", { 'haven_id': havenId }, function(status, data) {
		if (status == 200) {
			var options = "<option value='0'>----</option>"
			for (var loop = 0; loop < data['monsters'].length; loop++) {
				var dict = data['monsters'][loop];
				options += "<option value='" + dict.id + "'>" + dict.name + "</option>"
			}

			var picker = document.getElementById("monster");
			picker.innerHTML = options;
		}
	});
}

function fetchPuzzles(havenId) {
	postData("/haven/puzzles", { 'haven_id': havenId }, function(status, data) {
		if (status == 200) {
			var options = "<option value='0'>----</option>"
			for (var loop = 0; loop < data['puzzles'].length; loop++) {
				var dict = data['puzzles'][loop];
				options += "<option value='" + dict.id + "'>" + dict.name + "</option>"
			}

			var picker = document.getElementById("puzzle");
			picker.innerHTML = options;
		}
	});
}

window.onload = function() {
	canvas = document.getElementById("shardhavenMap");
	canvas_ctx = canvas.getContext('2d');
	canvas.addEventListener('click', function(event) {
		editRoom(event);
	}, false);

	picker = document.getElementById("shardhavenPicker");
	picker.onchange = function() {
		if (picker.value == 0) {
			havenId = 0;
			xDimension = 0;
			yDimension = 0;
			setupCanvas(0, 0, null)
			document.title = "Shardhaven Editor";
			setRoomData(null);
		}
		else {
			var havenName = picker.options[picker.selectedIndex].text;
			document.title = havenName + " - Shardhaven Editor"
			selectedX = null;
			selectedY = null;
			setRoomData(null);
			fetchHaven(picker.value);
			fetchObstacles(picker.value);
			fetchMonsters(picker.value);
			fetchPuzzles(picker.value);
		}
	};

	saveButton = document.getElementById("shardhavenRoomSave");
	saveButton.onclick = function() {
		saveRoom();
	};

	deleteButton = document.getElementById("shardhavenRoomDelete");
	deleteButton.onclick = function() {
		deleteRoom();
	}

	setRoomData(null);
	refreshHavenList();
}

