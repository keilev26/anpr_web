from connect import execute_query
# print(execute_query("insert into list_car (plate, user_id) values (%s,%s );", params=("CUB-604", 2), fetch=True))
# print(execute_query("insert into user (name,phone,email) values (%s,%s,%s);", params=("Caleb Camargo Saavedra","964136821","caleb.camargo.saavedra@uni.pe"), fetch=True))


# print(execute_query("INSERT INTO event_detection (plate) VALUES (%s);", params=("CUB-604",), fetch=True))
# print(execute_query("SHOW INDEX FROM event_detection; ;", fetch=True))
print(execute_query("select * from user;", fetch=True))
# print(execute_query("select * from list_car;", fetch=True)) 
