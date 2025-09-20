Twilio Flask App PoC

This is a Twilio-based phone call application using Flask. The app makes an outbound call, plays an initial instruction, asks three questions with a beep before each, records responses, and saves the entire call as a stereo MP3 file. It is designed for minimal delays and simplicity, with no retry logic for unanswered questions.

Features

Initial Instruction: Says “Please find a quiet place and answer each question after the beep” once at the start.

Questions: Asks in sequence:

“Please say your name.”

“Please say your age.”

“Do you want to book an appointment?”

Beep: Plays a beep before each question to signal when to answer.

Flow: Proceeds to the next question after each response (or silence), ends with “Thank you. Goodbye!”

Recording: Saves a single stereo MP3 file (192kbps, +5dB) in the recordings directory.

Environment: Uses dev.env for Twilio credentials and ngrok URL, tested with +919989135447.

Deployment: Local Flask server with ngrok for webhook exposure.
