'use strict'

const express = require('express')
const bodyParser = require('body-parser');

const fs = require('fs')


var app = express()

app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: false }))

// Serve static files
app.use(express.static('public'));  

const server = app.listen(5678); //start the server
console.log('Server is running...');
console.log('http://localhost:' + server.address().port)