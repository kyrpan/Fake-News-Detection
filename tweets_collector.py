import tweepy
from pymongo import MongoClient, DESCENDING
from tweepy import OAuthHandler
from pprint import pprint
import matplotlib.pyplot as plt   
import time
import collections
import pickle
import os
import sys
import networkx as nx
import pandas as pd

# connect to mongo
client = MongoClient('localhost', 27017)
db = client.FakeNews

def get_followers_of_user(api, name, user_id, users_per_page=5000):
    page = 1
    tweets = api.followers_ids(id=user_id, page=page, count=users_per_page)
    print(len(tweets['ids']))
    print(tweets['ids'])

    while len(tweets) > 0:
        page = page + 1
        print('page++')
        tweets = api.followers_ids(id=user_id, page=page, count=users_per_page)
        print(len(tweets['ids']))
        print(tweets['ids'])


def collect_tweets_of_user(api, name, user_id, tweets_per_page=200):
    page = 1
    tweets = api.user_timeline(id=user_id, page=page, count=tweets_per_page)
    for tweet in tweets:
        db[name].insert_one(tweet)
    while len(tweets) > 0:
        page = page + 1
        tweets = api.user_timeline(id=user_id, page=page, count=tweets_per_page)
        for tweet in tweets:
            db[name].insert_one(tweet)


def collect_retweets_of_a_tweet(api, initial_id, name, tweets_per_page=100):
    print("Getting retweets of {}".format(initial_id))

    page = 1
    retweets = api.retweets(id=initial_id, page=page, count=tweets_per_page)
    count = 0
    for tweet in retweets:
        db[name+'_retweets'].insert_one(tweet)
        count += 1

    while len(retweets) > 0:
        page = page + 1
        retweets = api.retweets(id=initial_id, page=page, count=tweets_per_page)
        for tweet in retweets:
            db[name + '_retweets'].insert_one(tweet)
            count += 1

    print("Collected {} retweets".format(count))

def collect_initial_tweets(api):
    collect_tweets_of_user(api, 'fake', '735574058167734273')
    #collect_tweets_of_user(api, 'real', '5402612')


def get_top_k(collection_name, field_name, limit):
    return db[collection_name].find().sort([[field_name, DESCENDING]]).limit(limit)


def get_retweets_of_tweet(collection_name, id, limit = 180):
    if limit == 0:
        return db[collection_name].find({'retweeted_status.id_str': id})
    else:
        return db[collection_name].find({'retweeted_status.id_str': id}).limit(limit)


def check_friendship(api, userA, userB):
    try:
        return api.show_friendship(source_id=userA, target_id=userB)
    except tweepy.TweepError:
        print("Failed to run the command on that user, Skipping...")
        return 'none'

def get_users_who_retweeted(collection_name, id):
    ids = []
    for tweet in get_retweets_of_tweet(collection_name, id):
        ids.append(tweet['user']['id'])
    return ids

#theo part
def find_user_per_hop(initial_user_id, users_that_retweeted, friendships=None):
    if friendships is None:
        friendships = collections.defaultdict(dict)

    all_users = [initial_user_id]
    all_users.extend(users_that_retweeted)

    for index, user1 in enumerate(all_users):
        for user2 in all_users[index+1:]:
            u1 = friendships[user1]

            if user2 in u1:
                continue

            friendship = check_friendship(api, user1, user2)
            
            if friendship is not "none" and friendship is not None:
                following = friendship['relationship']['source']['following']
                followed = friendship['relationship']['source']['followed_by']
                
                friendships[user1][user2] = followed or following
                friendships[user2][user1] = followed or following
            else:
                friendships[user1][user2] = False
                friendships[user2][user1] = False
    
    number_of_hops = 5
    hop_counters = {}
    hop_users = {}

    prev_no_relation = users_that_retweeted
    prev_hop_users = [initial_user_id]
    try:

        for i in range(number_of_hops):
            print("HOP {}".format(i+1))

            hop_counters[i] = 0
            hop_users[i] = set()

            current_hop_users = set()
            current_no_relation = set()

            print("Users not in previous relation: {}".format(len(prev_no_relation)))
            print("Previous Hop users: {}".format(len(prev_hop_users)))

            for user in prev_no_relation:
                for source_user in prev_hop_users:

                    if source_user not in friendships[user]:
                        friendship = check_friendship(api, user, source_user)
                        if friendship == "none":
                            continue
                        else:
                            following = friendship['relationship']['source']['following']
                            followed = friendship['relationship']['source']['followed_by']

                            friendships[user][source_user] = followed or following
                            friendships[source_user][user] = followed or following

                    if friendships[user][source_user]:
                        # Friends
                        hop_counters[i] += 1
                        hop_users[i].add(user)
                        
                    else:
                        current_no_relation.add(user)

            prev_hop_users = hop_users[i]
            for user in hop_users[i]:
                if user in current_no_relation:
                    current_no_relation.remove(user)

            prev_no_relation = current_no_relation

            print("\t{} Hops".format(hop_counters[i]))
    except KeyboardInterrupt as e:
        print("KeyboardInterrupt caught - saving friendships dict")        
        pickle.dump(friendships, open("friendships.pickle", "wb"), 2)
        sys.exit(1)
    except Exception as e:
        print("Exception caught - saving friendships dict")        
        print(e)
        pickle.dump(friendships, open("friendships.pickle", "wb"), 2)
        sys.exit(1)
        
    pickle.dump(friendships, open("friendships.pickle", "wb"), 2)
    return friendships, hop_counters, hop_users

def plot_retweets_over_time(top3, collection_name, on_fake):
    for index, tweet in enumerate(top3):
        Y_time = []
        tokens = (tweet['created_at']).split(' ')
        hour = tokens[3].split(":")
        month = str(time.strptime(tokens[1], '%b').tm_mon)
        if int(month) < 10:
            stamp = tokens[5]+'-0'+month+'-'+tokens[2]+'-'+hour[0] #get timestamp with 1 hour accuracy
        else:
            stamp = tokens[5]+'-'+month+'-'+tokens[2]+'-'+hour[0] #get timestamp with 1 hour accuracy

        Y_time.append(stamp) #initial timestamp of tweet
        collection = db[collection_name]
        cursor = collection.find({})

        for retweet in cursor:
            rt_status = retweet['retweeted_status']
            if rt_status['id_str'] == tweet['id_str'] : 
                tokens = (retweet['created_at']).split(" ")
                hour = tokens[3].split(":")
                month = str(time.strptime(tokens[1], '%b').tm_mon)
                if int(month) < 10:
                    stamp = tokens[5]+'-0'+month+'-'+tokens[2]+'-'+hour[0] #get timestamp with 1 hour accuracy
                else:
                    stamp = tokens[5]+'-'+month+'-'+tokens[2]+'-'+hour[0] #get timestamp with 1 hour accuracy
                Y_time.append(stamp) #timestamps of retweets

        df = pd.DataFrame(Y_time, columns=['timestamp'])

        df = df.groupby(df.columns.tolist(),as_index=False).size() #remove duplicates and keep count
        series = pd.Series(df)

        #print series
        plt.clf()
        plt.gcf().subplots_adjust(bottom=0.275)        

        # series.plot()

        prefix = "Fake"
        if not on_fake:
            prefix = "True"

        plt.ylabel('Retweet Count')
        plt.xlabel('Date Time')
        plt.plot(list(series.axes[0]), list(series))
        plt.xticks(list(series.axes[0])[::8], rotation=45)
        plt.title('{} Retweets VS Time'.format(prefix))
        plt.savefig(prefix.lower()+"_{}_retweets.png".format(index+1))


if __name__ == '__main__':
    
    # private keys: create an app on apps.twitter.com
    consumer_key = 'FkXH9u9z4erMLKVXCSBN8NQIB'
    consumer_secret = 'kbvQVKi6qYfnmx87vKNroCJxJ84x9h8KGRVp3A1cSborZ3ft87'
    access_token = '978456990-19gBiHo7yciV0Fqfh2OKQ7MF5tISqxYOebC6BhCZ'
    access_secret = 'mXW4LhnV85x5bsqfPUyCOhsnZf8iRYmxllOQG5dg6NwCu'

    # connecting to twitter
    auth = OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)
    api = tweepy.API(auth,
                     wait_on_rate_limit=True,
                     wait_on_rate_limit_notify=True,
                     parser=tweepy.parsers.JSONParser())

    collect = False
    
    if collect:

        # COLLECTING INITIAL TWEETS
        collect_initial_tweets(api)

        top3RealTweets = get_top_k('real', 'retweet_count', 3)
        top3FalseTweets = get_top_k('fake', 'retweet_count', 10) # Getting 10 since many have few retweets

        # COLLECTING RETWEETS
        for tweet in top3RealTweets:
           print(tweet)
           collect_retweets_of_a_tweet(api, tweet['id_str'], 'real')

        for tweet in top3FalseTweets:
            print(tweet)
            collect_retweets_of_a_tweet(api, tweet['id_str'], 'fake')

top3RealTweets = get_top_k('real', 'retweet_count', 3)
top3FalseTweets = get_top_k('fake', 'retweet_count', 10)

pickled_friendships = None
if os.path.exists("friendships.pickle"):
    pickled_friendships = pickle.load(open("friendships.pickle", "rb"))

top_3_real = []
for index, tweet in enumerate(top3RealTweets):
    print("Real Tweet: {}".format(index+1))
    top_3_real.append(tweet)

    initial_user_id = tweet['user']['id']
    users_that_retweeted = get_users_who_retweeted('real_retweets', tweet['id_str'])

    friendships, hop_counters, hop_users = find_user_per_hop(initial_user_id, users_that_retweeted, friendships=pickled_friendships)
    pickled_friendships = friendships

    x = [int(v) for v in list(range(1, len(hop_counters)+1))]
    y = [hop_counters[i-1] for i in x]

    plt.clf()
    plt.plot(x, y)
    plt.xticks(x)
    plt.title("Real Tweet " + str(index+1))
    plt.xlabel("Hops")
    plt.ylabel("Users per hop")
    plt.savefig("real_hops_{}.png".format(index+1))
    
    user_graph = nx.Graph() 
    user_graph.add_node(initial_user_id)
    for hop in hop_users:
        for hop_user in hop_users[hop]:
            user_graph.add_node(hop_user)
    
    for u_index, user1 in enumerate(list(user_graph.nodes)):
        for user2 in list(user_graph.nodes)[u_index+1:]:
            if friendships[user1][user2] or friendships[user2][user1]:
                user_graph.add_edge(user1, user2) 

    plt.clf()
    nx.draw(user_graph)
    plt.savefig("user_graph_real_{}.png".format(index+1))

plot_retweets_over_time(top_3_real, "real_retweets", False)

# Some fake news, although retrieved order based on number of retweets, 
# might not have many retweets - get ones with more than 50.
count = 0
proper_top_3_fake = []
for index, tweet in enumerate(top3FalseTweets):
    print("Fake Tweet: {}, {}".format(index+1, tweet["id_str"]))
    initial_user_id = tweet['user']['id']
    users_that_retweeted = get_users_who_retweeted('fake_retweets', tweet['id_str'])
    
    if len(users_that_retweeted) < 50:
        print("Skipping tweet {} - less than 50 users retweeted ({})".format(tweet['id_str'], len(users_that_retweeted)))
        continue

    proper_top_3_fake.append(tweet)

    friendships, hop_counters, hop_users = find_user_per_hop(initial_user_id, users_that_retweeted, friendships=pickled_friendships)
    pickled_friendships = friendships
    
    x = [int(v) for v in list(range(1, len(hop_counters)+1))]
    y = [hop_counters[i-1] for i in x]

    plt.clf()
    plt.plot(x, y)
    plt.xticks(x)
    plt.title("Fake Tweet " + str(count+1))
    plt.xlabel("Hops")
    plt.ylabel("Users per hop")
    plt.savefig("fake_hops_{}.png".format(count+1))

    user_graph = nx.Graph() 
    user_graph.add_node(initial_user_id)
    for hop in hop_users:
        for hop_user in hop_users[hop]:
            user_graph.add_node(hop_user)
        
    for u_index, user1 in enumerate(list(user_graph.nodes)):
        for user2 in list(user_graph.nodes)[u_index+1:]:
            if friendships[user1][user2] or friendships[user2][user1]:
                user_graph.add_edge(user1, user2)

    plt.clf()
    nx.draw(user_graph)
    plt.savefig("user_graph_fake_{}.png".format(count+1))


    count += 1
    if count == 3:
        break

plot_retweets_over_time(proper_top_3_fake, "fake_retweets", True)
