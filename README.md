------------------------ *Property Manager by Mark Lasal - ML -* --------------------------------------------


#                       ML Property Availability 


## Solution : 
   Check if any apartments is available (free or not already booked) given the user's dates and numeber of guest
   It loads the booking data from Google spreadsheets to a DWH featured by :-) **sqlite3** relational database in memory.
   
   Running simple SQL on the just created relational DB, the app shows:
   
   - the list of the available apartments
       
   - the detailed calendar overview focused on the user stay's selected dates +/- some days
       

   The solution wants as inputs:
   - GoogleSheets where are tracked all the historical bookings, past and future
   - "Structures": python list of Structures to manage. Each Structure is described (name, spreadsheet name, ... ) as a python dictionary  

   The user interaction and presentation is designed on **streamlit**.
   
   The tech stack is:
   - **gsspread**: to manage google sheets
   - **sqlite3**: to create and manage the relational DB. The initial version create it in memory
   - **streamlit**: to manage simple multi-page web app for sharing the insights with users    
   
   The target deploy is on streamlit cloud
   


