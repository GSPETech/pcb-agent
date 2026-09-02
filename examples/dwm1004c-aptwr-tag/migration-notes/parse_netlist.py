test_code = "my_net = Net()\nU5 = Component(name='U5', pin_defs={'1': '1', '2': '2'}, pins={'1': my_net, '2': my_net})"
with open("test.zen", "w") as f:
    f.write(test_code)
