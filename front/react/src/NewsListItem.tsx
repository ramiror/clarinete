import React, { FC, useState, useRef, useEffect } from "react";
import { useDispatch } from 'react-redux'
import { makeStyles } from '@material-ui/core/styles';
import Button from '@material-ui/core/Button';
import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import Typography from '@material-ui/core/Typography';
import { Link } from "react-router-dom";
import MoveToInboxIcon from '@material-ui/icons/MoveToInbox';

import { NewsItem } from './newsSlice'
import { addURL } from './archivedSlice'

const useStyles = makeStyles({
  root: {
    minWidth: 275,
    margin: 8,
  },
  title: {
    fontSize: 14,
  },
});


const MAX_TITLE_HEIGHT = 65
const NewsListItem: FC<{news: NewsItem, selected: boolean}> = ({news, selected}) => {
  const classes = useStyles();
  const dispatch = useDispatch()

  const [wasSelected, setWasSelected] = useState(false)

  const titleRef = useRef(null)
  const [fontSize, setFontSize] = useState(0)
  useEffect(() => {
    if (!titleRef.current) return
    if (fontSize !== 0) return
    const node = titleRef.current as unknown as HTMLElement
    if (!node.parentNode) return
    let heightTitle = node.getBoundingClientRect().height
    let f = 24
    while (heightTitle > MAX_TITLE_HEIGHT) {
      node.style.fontSize = (--f) + 'px'
      heightTitle = node.getBoundingClientRect().height
    }
    setFontSize(f)
  }, [fontSize])
  const ref = useRef(null)
  if (selected && !wasSelected) {
    setTimeout(() => {
        if (!ref || !ref.current) {
          return
        }
        const bbox = (ref.current as any).getBoundingClientRect()
        if (bbox.top < 0) {
          window.scrollTo(window.scrollX, window.scrollY + bbox.top)
        }
        if (bbox.bottom > window.innerHeight) {
          window.scrollTo(window.scrollX, window.scrollY + bbox.bottom - window.innerHeight)
        }
    })
  }
  if (selected !== wasSelected) {
    setWasSelected(selected)
  }
  const top = [news.volanta, {
    0: '😄',
    1: '🙏',
    2: '😠',
    3: '😢',
  }[news.sentiment]].filter((x) => !!x).join(' | ')

  const bottom = [
    news.section,
    news.source,
    news.date ? new Intl.DateTimeFormat('es').format(new Date(news.date)) : '',
  ].filter((x) => !!x).join(' | ')
  return (
    <Card className={classes.root} style={{outline: selected ? 'solid': 'none'}} ref={ref}>
      <CardContent>
        <Typography className={classes.title} color="textSecondary" gutterBottom>
          {top}
          <Button onClick={() => dispatch(addURL(news.url))}><MoveToInboxIcon /></Button>
        </Typography>
        <Typography variant="h5" component="h2" ref={titleRef} style={{fontSize: fontSize || 24}}>
          <Link to={'/' + encodeURIComponent(news.url)} title={news.summary}>{news.title}</Link>
        </Typography>
        <Typography color="textSecondary">
          {bottom}
        </Typography>
      </CardContent>
    </Card>
  );
}
export default NewsListItem
