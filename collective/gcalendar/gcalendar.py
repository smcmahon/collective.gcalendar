from time import localtime

from zope.i18nmessageid import MessageFactory
from zope.component import getMultiAdapter

from Acquisition import aq_inner
from DateTime import DateTime
from Products.CMFCore.utils import getToolByName
# from Products.CMFPlone import PloneMessageFactory as _
from Products.CMFPlone.utils import safe_unicode
# from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five.browser import BrowserView
from Products.PythonScripts.standard import url_quote_plus


PLMF = MessageFactory('plonelocales')


def toampm(s):
    if s:
        t = (DateTime('1-1-2010 ' + s).AMPMMinutes())
        if t[0] == '0':
            t = t[1:]
        return t.replace(' ', '').replace('12:00am', '')
    return s


class GCalendarView(BrowserView):

    def __init__(self, context, request):
        """
        This will initialize context and request object as they are given as view multiadaption parameters.
        """
        self.context = context
        self.request = request

        context = aq_inner(self.context)
        self.calendar = getToolByName(context, 'portal_calendar')
        self._ts = getToolByName(context, 'translation_service')
        self.url_quote_plus = url_quote_plus

        self.now = localtime()
        self.yearmonth = yearmonth = self.getYearAndMonthToDisplay()
        self.year = year = yearmonth[0]
        self.month = month = yearmonth[1]

        self.showPrevMonth = yearmonth > (self.now[0] - 1, self.now[1])
        self.showNextMonth = yearmonth < (self.now[0] + 1, self.now[1])

        self.prevMonthYear, self.prevMonthMonth = self.getPreviousMonth(year, month)
        self.nextMonthYear, self.nextMonthMonth = self.getNextMonth(year, month)
        self.monthName = PLMF(self._ts.month_msgid(month),
                              default=self._ts.month_english(month))

    def ctool_getEventsForCalendar(self, month='1', year='2002', **kw):
        """ recreates a sequence of weeks, by days each day is a mapping.
            {'day': #, 'url': None}
        """
        year = int(year)
        month = int(month)
        # daysByWeek is a list of days inside a list of weeks, like so:
        # [[0, 1, 2, 3, 4, 5, 6],
        #  [7, 8, 9, 10, 11, 12, 13],
        #  [14, 15, 16, 17, 18, 19, 20],
        #  [21, 22, 23, 24, 25, 26, 27],
        #  [28, 29, 30, 31, 0, 0, 0]]
        daysByWeek = self.calendar._getCalendar().monthcalendar(year, month)
        weeks = []

        events = self.catalog_getevents(year, month, **kw)

        for week in daysByWeek:
            days = []
            for day in week:
                if events.has_key(day):
                    days.append(events[day])
                else:
                    days.append({'day': day, 'event': 0, 'eventslist': []})

            weeks.append(days)

        return weeks

    def catalog_getevents(self, year, month, **kw):
        """ given a year and month return a list of days that have events
        """
        # XXX: this method violates the rules for tools/utilities:
        # it depends on a non-utility tool
        year = int(year)
        month = int(month)
        last_day = self.calendar._getCalendar().monthrange(year, month)[1]
        first_date = self.calendar.getBeginAndEndTimes(1, month, year)[0]
        last_date = self.calendar.getBeginAndEndTimes(last_day, month, year)[1]

        query_args = {
            'portal_type': self.calendar.getCalendarTypes(),
            'review_state': self.calendar.getCalendarStates(),
            'start': {'query': last_date, 'range': 'max'},
            'end': {'query': first_date, 'range': 'min'},
            'sort_on': 'start'
        }
        query_args.update(kw)
        if getattr(self.context, 'gcviewpath', False):
            query_args['path'] = '/'.join(self.context.getPhysicalPath())

        ctool = getToolByName(self, 'portal_catalog')
        query = ctool(**query_args)

        # compile a list of the days that have events
        eventDays = {}
        for daynumber in range(1, 32):  # 1 to 31
            eventDays[daynumber] = {'eventslist': [],
                                    'event': 0,
                                    'day': daynumber}
        includedevents = []
        for result in query:
            if result.getRID() in includedevents:
                break
            else:
                includedevents.append(result.getRID())
            event = {}
            # we need to deal with events that end next month
            if  result.end.month() != month:
                # doesn't work for events that last ~12 months
                # fix it if it's a problem, otherwise ignore
                eventEndDay = last_day
                event['end'] = None
            else:
                eventEndDay = result.end.day()
                event['end'] = result.end.Time()
            # and events that started last month
            if result.start.month() != month:  # same as above (12 month thing)
                eventStartDay = 1
                event['start'] = None
            else:
                eventStartDay = result.start.day()
                event['start'] = result.start.Time()

            event['title'] = result.Title or result.getId
            event['desc'] = result.Description
            event['url'] = result.getURL()

            if eventStartDay != eventEndDay:
                allEventDays = range(eventStartDay, eventEndDay + 1)
                eventDays[eventStartDay]['eventslist'].append(
                        {'end': None,
                         'start': result.start.Time(),
                         'title': event['title'],
                         'desc': event['desc'],
                         'url': event['url']})
                eventDays[eventStartDay]['event'] = 1

                for eventday in allEventDays[1:-1]:
                    eventDays[eventday]['eventslist'].append(
                        {'end': None,
                         'start': None,
                         'title': event['title'],
                          'desc': event['desc'],
                          'url': event['url']})
                    eventDays[eventday]['event'] = 1

                if result.end == result.end.earliestTime():
                    last_day_data = eventDays[allEventDays[-2]]
                    last_days_event = last_day_data['eventslist'][-1]
                    last_days_event['end'] = (result.end - 1).latestTime().Time()
                else:
                    eventDays[eventEndDay]['eventslist'].append(
                        {'end': result.end.Time(),
                         'start': None, 'title': event['title'],
                         'desc': event['desc'],
                         'url': event['url']})
                    eventDays[eventEndDay]['event'] = 1
            else:
                eventDays[eventStartDay]['eventslist'].append(event)
                eventDays[eventStartDay]['event'] = 1
            # This list is not uniqued and isn't sorted
            # uniquing and sorting only wastes time
            # and in this example we don't need to because
            # later we are going to do an 'if 2 in eventDays'
            # so the order is not important.
            # example:  [23, 28, 29, 30, 31, 23]
        return eventDays

    def getEventsForCalendar(self):
        context = aq_inner(self.context)
        year = self.year
        month = self.month
        portal_state = getMultiAdapter((self.context, self.request), name=u'plone_portal_state')
        navigation_root_path = portal_state.navigation_root_path()
        weeks = self.ctool_getEventsForCalendar(month, year, path=navigation_root_path)
        for week in weeks:
            for day in week:
                daynumber = day['day']
                if daynumber == 0:
                    continue
                day['is_today'] = self.isToday(daynumber)
                if day['event']:
                    cur_date = DateTime(year, month, daynumber)
                    localized_date = [self._ts.ulocalized_time(cur_date, context=context, request=self.request)]
                    for e in day['eventslist']:
                        e['start'] = toampm(e['start'])
                        e['end'] = toampm(e['end'])
                    day['eventstring'] = '\n'.join(localized_date + \
                        [' %s' % self.getEventString(e) for e in day['eventslist']])
                    day['date_string'] = '%s-%s-%s' % (year, month, daynumber)
        return weeks

    def getEventString(self, event):
        start = event['start'] and ':'.join(event['start'].split(':')[:2]) or ''
        end = event['end'] and ':'.join(event['end'].split(':')[:2]) or ''
        title = safe_unicode(event['title']) or u'event'
  
        if start and end:
            eventstring = "%s-%s %s" % (start, end, title)
        elif start:  # can assume not event['end']
            eventstring = "%s - %s" % (start, title)
        elif event['end']:  # can assume not event['start']
            eventstring = "%s - %s" % (title, end)
        else:  # can assume not event['start'] and not event['end']
            eventstring = title
  
        return eventstring
  
    def getYearAndMonthToDisplay(self):
        session = None
        request = self.request
  
        # First priority goes to the data in the REQUEST
        year = request.get('year', None)
        month = request.get('month', None)
  
        # Next get the data from the SESSION
        if self.calendar.getUseSession():
            session = request.get('SESSION', None)
            if session:
                if not year:
                    year = session.get('calendar_year', None)
                if not month:
                    month = session.get('calendar_month', None)
  
        # Last resort to today
        if not year:
            year = self.now[0]
        if not month:
            month = self.now[1]
  
        year, month = int(year), int(month)
  
        # Store the results in the session for next time
        if session:
            session.set('calendar_year', year)
            session.set('calendar_month', month)
  
        # Finally return the results
        return year, month
  
    def getPreviousMonth(self, year, month):
        if month == 0 or month == 1:
            month, year = 12, year - 1
        else:
            month -= 1
        return (year, month)
  
    def getNextMonth(self, year, month):
        if month == 12:
            month, year = 1, year + 1
        else:
            month += 1
        return (year, month)
  
    def getWeekdays(self):
        """Returns a list of Messages for the weekday names."""
        weekdays = []
        # list of ordered weekdays as numbers
        for day in self.calendar.getDayNumbers():
            weekdays.append(PLMF(self._ts.day_msgid(day, format='s'),
                                 default=self._ts.weekday_english(day, format='a')))
        return weekdays
  
    def isToday(self, day):
        """Returns True if the given day and the current month and year equals
           today, otherwise False.
        """
        return self.now[2] == day and self.now[1] == self.month and \
               self.now[0] == self.year
  
    def getReviewStateString(self):
        states = self.calendar.getCalendarStates()
        return ''.join(map(lambda x: 'review_state=%s&amp;' % self.url_quote_plus(x), states))
  
    def getQueryString(self):
        request = self.request
        query_string = request.get('orig_query',
                                   request.get('QUERY_STRING', None))
        if len(query_string) == 0:
            query_string = ''
        else:
            query_string = '%s&amp;' % query_string
        return query_string

    def testme(self):
        """
        Test Code
        """
        return self.monthName
